# Bot Discord pour allumer / éteindre le serveur de jeu

Un bot Discord ([files/power_bot.py](files/power_bot.py)) qui permet à tes amis d'**allumer le serveur gaming**
(Wake-on-LAN), de voir son état et de **démarrer / arrêter les jeux**, et à toi de l'**éteindre**.

| Commande | Qui | Effet |
|---|---|---|
| `/serveur statut` | Joueurs | Serveur allumé ou éteint, état de chaque jeu |
| `/serveur allumer` | Joueurs | Réveille le serveur (Wake-on-LAN) et attend qu'il réponde |
| `/jeu demarrer <jeu>` | Joueurs | Démarre la VM du jeu, en réveillant le serveur si besoin |
| `/jeu arreter <jeu>` | Joueurs | Arrête proprement la VM du jeu |
| `/serveur eteindre` | Admins seulement | Arrête le serveur (Proxmox arrête d'abord les VMs proprement) |

```
Discord ◄──── connexion sortante ──── LXC power-bot (Proxmox principal, 192.168.1.70)
                                         │ Wake-on-LAN (broadcast réseau local)
                                         │ API Proxmox (token limité à l'alimentation)
                                         ▼
                                Proxmox gaming (192.168.1.125) ──► VMs enshrouded, assetto, beamng
```

**Sécurité** :
- **Discord authentifie les utilisateurs** ; le bot vérifie le serveur Discord, le rôle « joueur » et la liste des admins.
  Ses commandes n'existent que sur ton serveur Discord, et un refus est noté dans les logs.
- Le bot se connecte **lui-même** à Discord : **aucun port à ouvrir** sur la Freebox.
- Le token Proxmox du bot ne peut **que** allumer/éteindre et lire l'état (pas de console, disque, création de VM).
- Les secrets (token Discord, token Proxmox) sont dans un vault Ansible, et sur le conteneur dans un fichier root `0600`.
- Les jeux sont trouvés par leur **tag Proxmox** (`enshrouded`, `assetto`, `beammp`) : rien à changer si une VM est recréée.

---

## 1. Créer le bot Discord

1. Sur le [portail développeur Discord](https://discord.com/developers/applications) : **New Application** (nom : « Serveur de jeu » par exemple).
2. Onglet **Bot** : **Reset Token** et copier le token (il ne sera plus affiché). Aucun « Privileged Gateway Intent » n'est nécessaire.
3. Onglet **OAuth2 → URL Generator** : cocher les scopes **`bot`** et **`applications.commands`**, permission **Send Messages**,
   ouvrir l'URL générée et inviter le bot sur ton serveur Discord.
4. Sur ton serveur Discord : créer un rôle **Joueurs** et le donner à tes amis.
5. Activer le **mode développeur** (Paramètres utilisateur → Avancés), puis clic droit → **Copier l'identifiant** sur :
   ton serveur Discord, le rôle Joueurs, ton propre profil.

## 2. Activer le Wake-on-LAN sur le serveur gaming

1. **BIOS/UEFI** du serveur gaming : activer *Wake on LAN* / *Power On By PCI-E*, désactiver *ErP* s'il existe
   (il coupe l'alimentation de la carte réseau à l'arrêt).
2. **Carte réseau** : dans le shell du Proxmox gaming (interface web → nœud **game** → **Shell**), trouver l'interface
   physique (celle du pont `vmbr0`, par exemple `enp5s0`) et son adresse MAC :
   ```bash
   ip -br link
   ```
   puis activer le WoL, de façon permanente : dans `/etc/network/interfaces`, sous `iface vmbr0 inet static`, ajouter
   ```
   post-up /usr/sbin/ethtool -s enp5s0 wol g
   ```
   (`apt install ethtool` si besoin). Vérifier : `ethtool enp5s0 | grep Wake-on` doit afficher `Wake-on: g`.
3. **Tester** : éteindre le serveur gaming, puis depuis le Proxmox principal :
   ```bash
   apt install wakeonlan && wakeonlan <MAC>
   ```
   Le serveur doit démarrer. Si ce test échoue, le bot ne pourra pas l'allumer non plus.

## 3. Créer le token Proxmox du bot (serveur gaming)

Dans le shell du Proxmox gaming :
```bash
pveum role add PowerBot -privs "Sys.Audit Sys.PowerMgmt VM.Audit VM.PowerMgmt"
```
```bash
pveum user add powerbot@pve --comment "Discord power bot"
```
```bash
pveum acl modify / --users powerbot@pve --roles PowerBot
```
```bash
pveum user token add powerbot@pve bot --privsep 0
```
Copier le secret affiché (une seule fois). L'identifiant du token est `powerbot@pve!bot`.

## 4. Créer le conteneur LXC (Proxmox principal)

Interface du Proxmox principal → **Create CT** :
- Hostname `power-bot`, **unprivileged**, mot de passe root + **ta clé SSH publique** (`cat ~/.ssh/id_ed25519.pub` dans WSL) ;
- Template **Debian 13** ;
- 1 cœur, 512 Mo de RAM, 4 Go de disque ;
- Réseau `vmbr0` (le même réseau local que le serveur gaming), **IP fixe** (ex. `192.168.1.230/24`, passerelle `192.168.1.254` ou celle de ta box) ;
- Dans les options du conteneur : **Tags** `power_bot`, et **Start at boot** activé.

Démarrer le conteneur, puis accepter son empreinte SSH une fois : `ssh root@<ip du conteneur>`.

## 5. Configurer et déployer

1. **Vault** (id `power_bot`), une seule fois, depuis WSL :
   ```bash
   openssl rand -base64 32 > ~/.ansible_vault_credentials/.ansible_vault_power_bot.pass && chmod 600 ~/.ansible_vault_credentials/.ansible_vault_power_bot.pass
   ```
   ajouter `power_bot@~/.ansible_vault_credentials/.ansible_vault_power_bot.pass` à `vault_identity_list` dans
   `ansible.cfg`, puis depuis `ansible/` :
   ```bash
   mkdir -p inventories/group_vars/group_power_bot && poetry run ansible-vault create inventories/group_vars/group_power_bot/vault.yml --encrypt-vault-id power_bot
   ```
   ```yaml
   power_bot_discord_token: <token du bot Discord>
   power_bot_proxmox_token_secret: <secret du token Proxmox>
   ```
2. **Réglages** (non secrets) dans `inventories/group_vars/group_power_bot/main.yml` :
   ```yaml
   power_bot_discord_guild_id: 123456789012345678
   power_bot_discord_player_role_ids:
     - 234567890123456789   # rôle Joueurs
   power_bot_discord_admin_user_ids:
     - 345678901234567890   # toi
   power_bot_wol_mac: "aa:bb:cc:dd:ee:ff"
   ```
3. **Déployer** :
   ```bash
   poetry run ansible-playbook power_bot.yml
   ```
4. **Vérifier**, sur le conteneur : `journalctl -u power-bot -f` doit afficher « Commands synchronized on guild ... ».
   Les commandes apparaissent dans Discord en tapant `/`.

## 6. Réglages

| Variable | Défaut | Rôle |
|---|---|---|
| `power_bot_games` | `enshrouded`, `assetto`, `beammp` | Jeux proposés = tags Proxmox des VMs |
| `power_bot_boot_timeout` | `300` | Secondes d'attente du démarrage après un Wake-on-LAN |
| `power_bot_wol_broadcast` | `192.168.1.255` | Adresse de broadcast du réseau local |
| `power_bot_proxmox_url` / `_node` | `https://192.168.1.125:8006` / `game` | Proxmox gaming |
| `power_bot_proxmox_verify_tls` | `false` | Certificat auto-signé du Proxmox sur le réseau local |

Pour ajouter un jeu : mettre un tag à sa VM dans Proxmox, l'ajouter à `power_bot_games`, redéployer.

## 7. Développement

Tests unitaires (sans Discord ni Proxmox, avec un faux serveur Proxmox local), depuis WSL :
```bash
python3 -m venv ~/.cache/power-bot-test-venv && ~/.cache/power-bot-test-venv/bin/pip install -r roles/power_bot/files/requirements.txt
```
```bash
cd roles/power_bot/tests && ~/.cache/power-bot-test-venv/bin/python -m unittest -v test_power_bot
```
