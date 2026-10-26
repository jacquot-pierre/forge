"""Unit tests of the power bot (no Discord nor real Proxmox needed).

Run from this folder, in a virtualenv with the bot requirements installed:
    python -m unittest -v test_power_bot
"""

import asyncio
import socket
import sys
import unittest
from pathlib import Path

from aiohttp import ClientSession, web

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "files"))

import power_bot  # noqa: E402

ENV = {
    "DISCORD_TOKEN": "token",
    "DISCORD_GUILD_ID": "1000",
    "DISCORD_PLAYER_ROLE_IDS": "2000, 2001",
    "DISCORD_ADMIN_USER_IDS": "3000",
    "PROXMOX_URL": "https://192.168.1.125:8006/",
    "PROXMOX_TOKEN_ID": "powerbot@pve!bot",
    "PROXMOX_TOKEN_SECRET": "secret",
    "WOL_MAC": "AA:BB:CC:DD:EE:FF",
    "GAMES": "enshrouded,assetto,beammp",
}


class MagicPacketTest(unittest.TestCase):
    def test_formats(self):
        expected = b"\xff" * 6 + bytes.fromhex("aabbccddeeff") * 16
        for mac in ("aa:bb:cc:dd:ee:ff", "AA-BB-CC-DD-EE-FF", "aabbccddeeff", " AA:BB:CC:DD:EE:FF "):
            self.assertEqual(power_bot.magic_packet(mac), expected, mac)
        self.assertEqual(len(expected), 102)

    def test_invalid(self):
        for mac in ("", "aa:bb:cc:dd:ee", "gg:bb:cc:dd:ee:ff", "aa:bb-cc:dd:ee:ff", "aa:bb:cc:dd:ee:ff:00"):
            with self.assertRaises(ValueError, msg=mac):
                power_bot.magic_packet(mac)

    def test_send_wol(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as listener:
            listener.bind(("127.0.0.1", 0))
            listener.settimeout(2)
            power_bot.send_wol("aa:bb:cc:dd:ee:ff", "127.0.0.1", listener.getsockname()[1])
            self.assertEqual(listener.recv(200), power_bot.magic_packet("aa:bb:cc:dd:ee:ff"))


class ConfigTest(unittest.TestCase):
    def test_from_env(self):
        config = power_bot.Config.from_env(ENV)
        self.assertEqual(config.guild_id, 1000)
        self.assertEqual(config.player_role_ids, {2000, 2001})
        self.assertEqual(config.admin_user_ids, {3000})
        self.assertEqual(config.proxmox_url, "https://192.168.1.125:8006")
        self.assertEqual(config.proxmox_node, "game")
        self.assertFalse(config.proxmox_verify_tls)
        self.assertEqual(config.games, ("enshrouded", "assetto", "beammp"))
        self.assertEqual(config.boot_timeout, 300)

    def test_missing(self):
        env = dict(ENV, DISCORD_TOKEN="")
        with self.assertRaisesRegex(ValueError, "DISCORD_TOKEN"):
            power_bot.Config.from_env(env)

    def test_bad_mac_and_no_game(self):
        with self.assertRaises(ValueError):
            power_bot.Config.from_env(dict(ENV, WOL_MAC="nope"))
        with self.assertRaisesRegex(ValueError, "GAMES"):
            power_bot.Config.from_env(dict(ENV, GAMES=" , "))

    def test_permissions(self):
        config = power_bot.Config.from_env(ENV)
        # Players: right guild + player role, or admin
        self.assertTrue(config.can_play(1000, 42, {2001}))
        self.assertTrue(config.can_play(1000, 3000, set()))
        self.assertFalse(config.can_play(1000, 42, {9999}))
        self.assertFalse(config.can_play(1001, 42, {2000}))  # another Discord server
        self.assertFalse(config.can_play(None, 3000, set()))  # direct message
        # Shut down: admins only, right guild only
        self.assertTrue(config.can_admin(1000, 3000))
        self.assertFalse(config.can_admin(1000, 42))
        self.assertFalse(config.can_admin(1001, 3000))


class FindGameVmsTest(unittest.TestCase):
    def test_tags(self):
        vms = [
            {"vmid": 102, "name": "beamng", "tags": "base;beammp;docker", "status": "stopped"},
            {"vmid": 100, "name": "enshrouded", "tags": "base;docker;enshrouded;gaming", "status": "running"},
            {"vmid": 9000, "name": "template", "tags": "enshrouded", "template": 1},
            {"vmid": 105, "name": "enshrouded-test", "tags": "enshrouded"},
            {"vmid": 103, "name": "untagged"},
        ]
        found = power_bot.find_game_vms(vms, ("enshrouded", "assetto", "beammp"))
        self.assertEqual(found["enshrouded"]["vmid"], 100)  # lowest VM ID wins, template ignored
        self.assertEqual(found["beammp"]["vmid"], 102)
        self.assertNotIn("assetto", found)


class FakeProxmox:
    """Local HTTP server answering like the Proxmox API of node "game"."""

    def __init__(self):
        self.calls = []
        self.app = web.Application()
        self.app.router.add_route("*", "/{tail:.*}", self.handle)

    async def handle(self, request):
        self.calls.append((request.method, request.path, dict(await request.post()),
                           request.headers.get("Authorization")))
        if request.path == "/api2/json/nodes/game/qemu":
            return web.json_response({"data": [{"vmid": 100, "tags": "enshrouded", "status": "stopped"}]})
        return web.json_response({"data": None})


class ProxmoxClientTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.fake = FakeProxmox()
        self.runner = web.AppRunner(self.fake.app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        config = power_bot.Config.from_env(dict(ENV, PROXMOX_URL=f"http://127.0.0.1:{port}"))
        self.session = ClientSession()
        self.proxmox = power_bot.Proxmox(config, self.session)

    async def asyncTearDown(self):
        await self.session.close()
        await self.runner.cleanup()

    async def test_calls(self):
        self.assertTrue(await self.proxmox.is_up())
        self.assertEqual((await self.proxmox.game_vms())["enshrouded"]["vmid"], 100)
        await self.proxmox.start_vm(100)
        await self.proxmox.shutdown_vm(100)
        await self.proxmox.shutdown_node()
        self.assertEqual([(method, path, data) for method, path, data, _ in self.fake.calls], [
            ("GET", "/api2/json/nodes/game/status", {}),
            ("GET", "/api2/json/nodes/game/qemu", {}),
            ("POST", "/api2/json/nodes/game/qemu/100/status/start", {}),
            ("POST", "/api2/json/nodes/game/qemu/100/status/shutdown", {}),
            ("POST", "/api2/json/nodes/game/status", {"command": "shutdown"}),
        ])
        self.assertTrue(all(auth == "PVEAPIToken=powerbot@pve!bot=secret" for *_, auth in self.fake.calls))

    async def test_down(self):
        await self.runner.cleanup()  # nothing listens anymore: the server is off
        self.assertFalse(await self.proxmox.is_up())


class CommandsTest(unittest.TestCase):
    def test_groups(self):
        bot = power_bot.PowerBot(power_bot.Config.from_env(ENV))
        server = power_bot.build_server_group(bot)
        game = power_bot.build_game_group(bot)
        self.assertEqual(sorted(c.name for c in server.commands), ["allumer", "eteindre", "statut"])
        self.assertEqual(sorted(c.name for c in game.commands), ["arreter", "demarrer"])
        start = next(c for c in game.commands if c.name == "demarrer")
        self.assertEqual([choice.value for choice in start.parameters[0].choices], ["enshrouded", "assetto", "beammp"])
        asyncio.run(bot.close())


if __name__ == "__main__":
    unittest.main()
