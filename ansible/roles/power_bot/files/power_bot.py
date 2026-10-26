"""Discord bot powering the gaming Proxmox server on and off for a group of friends.

- Wakes the server up with Wake-on-LAN (it must run on the same LAN, e.g. the main Proxmox server).
- Talks to the Proxmox API of the gaming server with a token limited to power management.
- Game VMs are found by their Proxmox tag (one tag per game, e.g. "enshrouded").

Discord authenticates the users: the bot only checks the guild, the roles and the user IDs.
Configuration comes from environment variables (see Config.from_env).
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import socket
import sys
from dataclasses import dataclass

import aiohttp
import discord
from discord import app_commands

log = logging.getLogger("power_bot")

MAC_RE = re.compile(r"^[0-9a-f]{2}([:-]?)[0-9a-f]{2}(\1[0-9a-f]{2}){4}$")
STATE_LABELS = {"running": "🟢 démarrée", "stopped": "⚪ arrêtée", "paused": "🟡 en pause"}


# --- Pure logic (unit tested) -----------------------------------------------------------------------------------


def magic_packet(mac: str) -> bytes:
    """Wake-on-LAN magic packet: 6 x 0xFF then the MAC address repeated 16 times."""
    mac = mac.strip().lower()
    if not MAC_RE.match(mac):
        raise ValueError(f"invalid MAC address: {mac!r}")
    return b"\xff" * 6 + bytes.fromhex(re.sub(r"[:-]", "", mac)) * 16


def parse_ids(value: str) -> frozenset[int]:
    """Comma separated Discord IDs ("123,456") to a set of ints, empty items ignored."""
    return frozenset(int(item) for item in value.replace(" ", "").split(",") if item)


def parse_bool(value: str) -> bool:
    return value.strip().lower() in ("1", "true", "yes", "on")


def vm_tags(vm: dict) -> set[str]:
    """Proxmox returns the tags of a VM as a single "a;b;c" string."""
    return {tag for tag in str(vm.get("tags", "")).split(";") if tag}


def find_game_vms(vms: list[dict], games: tuple[str, ...]) -> dict[str, dict]:
    """Game name -> VM, a game being the VM tagged with its name (first match by VM ID)."""
    found: dict[str, dict] = {}
    for vm in sorted(vms, key=lambda vm: int(vm.get("vmid", 0))):
        if vm.get("template"):
            continue
        for game in games:
            if game in vm_tags(vm) and game not in found:
                found[game] = vm
    return found


@dataclass(frozen=True)
class Config:
    discord_token: str
    guild_id: int
    player_role_ids: frozenset[int]
    admin_user_ids: frozenset[int]
    proxmox_url: str
    proxmox_node: str
    proxmox_token_id: str
    proxmox_token_secret: str
    proxmox_verify_tls: bool
    wol_mac: str
    wol_broadcast: str
    games: tuple[str, ...]
    boot_timeout: int

    @classmethod
    def from_env(cls, env: dict[str, str]) -> Config:
        missing = [
            name
            for name in ("DISCORD_TOKEN", "DISCORD_GUILD_ID", "PROXMOX_URL", "PROXMOX_TOKEN_ID",
                         "PROXMOX_TOKEN_SECRET", "WOL_MAC")
            if not env.get(name)
        ]
        if missing:
            raise ValueError(f"missing environment variables: {', '.join(missing)}")
        config = cls(
            discord_token=env["DISCORD_TOKEN"],
            guild_id=int(env["DISCORD_GUILD_ID"]),
            player_role_ids=parse_ids(env.get("DISCORD_PLAYER_ROLE_IDS", "")),
            admin_user_ids=parse_ids(env.get("DISCORD_ADMIN_USER_IDS", "")),
            proxmox_url=env["PROXMOX_URL"].rstrip("/"),
            proxmox_node=env.get("PROXMOX_NODE", "game"),
            proxmox_token_id=env["PROXMOX_TOKEN_ID"],
            proxmox_token_secret=env["PROXMOX_TOKEN_SECRET"],
            proxmox_verify_tls=parse_bool(env.get("PROXMOX_VERIFY_TLS", "false")),
            wol_mac=env["WOL_MAC"],
            wol_broadcast=env.get("WOL_BROADCAST", "255.255.255.255"),
            games=tuple(game for game in env.get("GAMES", "").replace(" ", "").split(",") if game),
            boot_timeout=int(env.get("BOOT_TIMEOUT", "300")),
        )
        if not config.games:
            raise ValueError("GAMES is empty: list the Proxmox tags of the game VMs (e.g. enshrouded,assetto)")
        magic_packet(config.wol_mac)  # fail at startup on a bad MAC, not at the first wake up
        return config

    def can_play(self, guild_id: int | None, user_id: int, role_ids: set[int]) -> bool:
        """Wake the server, see its status, start and stop the game VMs."""
        if guild_id != self.guild_id:
            return False
        return user_id in self.admin_user_ids or bool(self.player_role_ids & role_ids)

    def can_admin(self, guild_id: int | None, user_id: int) -> bool:
        """Shut the whole server down."""
        return guild_id == self.guild_id and user_id in self.admin_user_ids


# --- Side effects ------------------------------------------------------------------------------------------------


def send_wol(mac: str, broadcast: str, port: int = 9) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(magic_packet(mac), (broadcast, port))


class Proxmox:
    """Minimal Proxmox API client (API token, only the calls the bot needs)."""

    def __init__(self, config: Config, session: aiohttp.ClientSession) -> None:
        self.config = config
        self.session = session
        self.base = f"{config.proxmox_url}/api2/json/nodes/{config.proxmox_node}"
        self.headers = {"Authorization": f"PVEAPIToken={config.proxmox_token_id}={config.proxmox_token_secret}"}
        self.ssl = None if config.proxmox_verify_tls else False

    async def _call(self, method: str, path: str, data: dict | None = None, timeout: float = 15):
        async with self.session.request(
            method, f"{self.base}{path}", headers=self.headers, data=data, ssl=self.ssl,
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as response:
            response.raise_for_status()
            return (await response.json())["data"]

    async def is_up(self) -> bool:
        try:
            await self._call("GET", "/status", timeout=5)
            return True
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
            return False

    async def game_vms(self) -> dict[str, dict]:
        return find_game_vms(await self._call("GET", "/qemu"), self.config.games)

    async def start_vm(self, vmid: int) -> None:
        await self._call("POST", f"/qemu/{vmid}/status/start")

    async def shutdown_vm(self, vmid: int) -> None:
        await self._call("POST", f"/qemu/{vmid}/status/shutdown")

    async def shutdown_node(self) -> None:
        await self._call("POST", "/status", data={"command": "shutdown"})


class PowerBot(discord.Client):
    def __init__(self, config: Config) -> None:
        # Only the (non privileged) guilds intent, needed by discord.py to track its state: no message content,
        # no member list, no presence
        intents = discord.Intents.none()
        intents.guilds = True
        super().__init__(intents=intents)
        self.config = config
        self.tree = app_commands.CommandTree(self)
        self.session: aiohttp.ClientSession | None = None
        self.proxmox: Proxmox | None = None
        self.wake_lock = asyncio.Lock()
        self.tree.on_error = self.on_tree_error

    async def setup_hook(self) -> None:
        self.session = aiohttp.ClientSession()
        self.proxmox = Proxmox(self.config, self.session)
        guild = discord.Object(id=self.config.guild_id)
        self.tree.add_command(build_server_group(self), guild=guild)
        self.tree.add_command(build_game_group(self), guild=guild)
        # Guild commands only: invisible and unusable from any other Discord server
        await self.tree.sync(guild=guild)
        log.info("Commands synchronized on guild %s", self.config.guild_id)

    async def close(self) -> None:
        if self.session:
            await self.session.close()
        await super().close()

    async def on_tree_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        """Any failure (Proxmox refusing, timeout...) answers the user instead of leaving them on "thinking"."""
        log.error("Command failed", exc_info=error)
        message = "❌ Erreur : le serveur Proxmox a refusé l'action ou n'a pas répondu. Préviens l'admin."
        if interaction.response.is_done():
            await interaction.followup.send(message)
        else:
            await interaction.response.send_message(message, ephemeral=True)

    async def authorize(self, interaction: discord.Interaction, admin: bool = False) -> bool:
        user = interaction.user
        role_ids = {role.id for role in getattr(user, "roles", [])}
        allowed = (
            self.config.can_admin(interaction.guild_id, user.id)
            if admin
            else self.config.can_play(interaction.guild_id, user.id, role_ids)
        )
        log.info("%s (%s) /%s -> %s", user, user.id, interaction.command.qualified_name if interaction.command else "?",
                 "allowed" if allowed else "denied")
        if not allowed:
            await interaction.response.send_message("⛔ Tu n'as pas le droit d'utiliser cette commande.", ephemeral=True)
        return allowed

    async def ensure_up(self, interaction: discord.Interaction) -> bool:
        """Wake the server up if needed and wait until its API answers."""
        assert self.proxmox
        async with self.wake_lock:  # several friends at once: a single wake up
            if await self.proxmox.is_up():
                return True
            send_wol(self.config.wol_mac, self.config.wol_broadcast)
            await interaction.followup.send(
                f"⏰ Le serveur dort, je le réveille (jusqu'à {self.config.boot_timeout // 60} min)..."
            )
            for _ in range(max(1, self.config.boot_timeout // 10)):
                await asyncio.sleep(10)
                if await self.proxmox.is_up():
                    return True
            return False


def state_label(vm: dict) -> str:
    return STATE_LABELS.get(vm.get("status", ""), vm.get("status", "inconnu"))


def build_server_group(bot: PowerBot) -> app_commands.Group:
    group = app_commands.Group(name="serveur", description="Serveur de jeu")

    @group.command(name="statut", description="Le serveur est-il allumé, quels jeux tournent ?")
    async def status(interaction: discord.Interaction) -> None:
        if not await bot.authorize(interaction):
            return
        await interaction.response.defer(thinking=True)
        if not await bot.proxmox.is_up():
            await interaction.followup.send("😴 Le serveur est **éteint**. `/serveur allumer` pour le réveiller.")
            return
        vms = await bot.proxmox.game_vms()
        lines = [f"• **{game}** : {state_label(vms[game])}" if game in vms else f"• **{game}** : VM introuvable"
                 for game in bot.config.games]
        await interaction.followup.send("✅ Le serveur est **allumé**.\n" + "\n".join(lines))

    @group.command(name="allumer", description="Réveille le serveur de jeu")
    async def wake(interaction: discord.Interaction) -> None:
        if not await bot.authorize(interaction):
            return
        await interaction.response.defer(thinking=True)
        if await bot.proxmox.is_up():
            await interaction.followup.send("✅ Le serveur est déjà allumé.")
        elif await bot.ensure_up(interaction):
            await interaction.followup.send("✅ Serveur allumé ! `/jeu demarrer` pour lancer un jeu.")
        else:
            await interaction.followup.send("❌ Le serveur ne répond toujours pas. Préviens l'admin.")

    @group.command(name="eteindre", description="Éteint le serveur de jeu (admin)")
    async def shutdown(interaction: discord.Interaction) -> None:
        if not await bot.authorize(interaction, admin=True):
            return
        await interaction.response.defer(thinking=True)
        if not await bot.proxmox.is_up():
            await interaction.followup.send("😴 Le serveur est déjà éteint.")
            return
        running = [game for game, vm in (await bot.proxmox.game_vms()).items() if vm.get("status") == "running"]
        await bot.proxmox.shutdown_node()
        suffix = f" Les jeux en cours ({', '.join(running)}) sont arrêtés proprement d'abord." if running else ""
        await interaction.followup.send(f"🛑 Arrêt du serveur demandé.{suffix}")

    return group


def build_game_group(bot: PowerBot) -> app_commands.Group:
    group = app_commands.Group(name="jeu", description="Serveurs de jeu")
    choices = [app_commands.Choice(name=game, value=game) for game in bot.config.games]

    @group.command(name="demarrer", description="Démarre un jeu (allume le serveur si besoin)")
    @app_commands.describe(jeu="Le jeu à démarrer")
    @app_commands.choices(jeu=choices)
    async def start(interaction: discord.Interaction, jeu: app_commands.Choice[str]) -> None:
        if not await bot.authorize(interaction):
            return
        await interaction.response.defer(thinking=True)
        if not await bot.ensure_up(interaction):
            await interaction.followup.send("❌ Le serveur ne répond pas, impossible de démarrer le jeu.")
            return
        vm = (await bot.proxmox.game_vms()).get(jeu.value)
        if vm is None:
            await interaction.followup.send(f"❌ Aucune VM avec le tag `{jeu.value}` sur le serveur.")
        elif vm.get("status") == "running":
            await interaction.followup.send(f"✅ **{jeu.value}** tourne déjà.")
        else:
            await bot.proxmox.start_vm(int(vm["vmid"]))
            await interaction.followup.send(
                f"🚀 **{jeu.value}** démarre. Le serveur de jeu sera joignable d'ici quelques minutes."
            )

    @group.command(name="arreter", description="Arrête un jeu")
    @app_commands.describe(jeu="Le jeu à arrêter")
    @app_commands.choices(jeu=choices)
    async def stop(interaction: discord.Interaction, jeu: app_commands.Choice[str]) -> None:
        if not await bot.authorize(interaction):
            return
        await interaction.response.defer(thinking=True)
        if not await bot.proxmox.is_up():
            await interaction.followup.send("😴 Le serveur est éteint, rien à arrêter.")
            return
        vm = (await bot.proxmox.game_vms()).get(jeu.value)
        if vm is None or vm.get("status") != "running":
            await interaction.followup.send(f"⚪ **{jeu.value}** ne tourne pas.")
        else:
            await bot.proxmox.shutdown_vm(int(vm["vmid"]))
            await interaction.followup.send(f"🛑 **{jeu.value}** s'arrête (sauvegarde du monde comprise).")

    return group


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        config = Config.from_env(dict(os.environ))
    except ValueError as error:
        log.error("Configuration error: %s", error)
        sys.exit(1)
    PowerBot(config).run(config.discord_token, log_handler=None)


if __name__ == "__main__":
    main()
