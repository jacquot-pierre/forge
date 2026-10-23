# forge-ansible
Ansible Forge to deploy infrastructure

# Configuration Ansible
Le repo est sur `/mnt/z` (dossier accessible en écriture à tous) : Ansible y ignore `ansible.cfg`.
Le désigner explicitement, une fois pour toutes, dans `~/.bashrc` :
```bash
export ANSIBLE_CONFIG=/mnt/z/forge/ansible/ansible.cfg
```

# Installation des dépendances
Installer poetry:
```bash
pipx install --python python3.13 poetry
```

Installer extension ansible:
```bash
poetry run ansible-galaxy collection install community.general
```

# List proxmox inventory
```bash
poetry run ansible-inventory -i inventories/inventory.proxmox.yaml --vars --graph --ask-vault-pass
```

# Serveurs Proxmox
Deux serveurs Proxmox indépendants sont déclarés, chacun avec ses deux inventaires dynamiques (LXC et VM) :

| Serveur | API | Inventaires |
|---|---|---|
| principal | 192.168.1.70:8006 | `inventory_lxc.proxmox.yaml`, `inventory_qemu.proxmox.yaml` |
| gaming | 192.168.1.125:8006 | `inventory_lxc.gaming.proxmox.yaml`, `inventory_qemu.gaming.proxmox.yaml` |

Les identifiants API des deux serveurs sont dans le même vault `inventories/group_vars/all/proxmox.yaml`.

## Ajouter le token lecture seule sur le serveur gaming
Sur le shell du Proxmox 192.168.1.125 :
```bash
pveum user add ansible@pve --comment "Ansible dynamic inventory"
pveum acl modify / --users ansible@pve --roles PVEAuditor
pveum user token add ansible@pve inventory --privsep 0
```
Puis ajouter ces clés dans le vault (`poetry run ansible-vault edit inventories/group_vars/all/proxmox.yaml`) :
```yaml
proxmox_gaming_readonly_url: https://192.168.1.125:8006
proxmox_gaming_readonly_user: ansible@pve
proxmox_gaming_readonly_token_id: inventory
proxmox_gaming_readonly_token_secret: <secret affiché par pveum>
```

# Configuration de base des VMs cloud-init
Le playbook `base.yml` configure les VMs clonées depuis le template Debian 13 cloud-init :
mise à jour, paquets de base, qemu-guest-agent, fuseau horaire, mises à jour de sécurité automatiques, TRIM, durcissement SSH (clé uniquement, root compris).

Il cible les VMs **démarrées** portant le tag Proxmox `base` (groupe `group_base`), sur les deux serveurs.
Mettre le tag `base` sur le template : chaque clone en hérite.

Prérequis sur la VM : IP fixe dans l'onglet Cloud-Init (`ipconfig0`), utilisateur cloud-init avec ta clé SSH
(utilisateur SSH défini par serveur via `ansible_user` dans `inventories/group_vars/proxmox_<nœud>_qemu.yaml` :
`machiki` sur gaming, `root` sur le principal).
Le login root est autorisé par clé uniquement sur toutes les VMs (`base_ssh_permit_root_login: no` pour l'interdire).

```bash
# Toutes les VMs "base" démarrées
poetry run ansible-playbook base.yml
# Une seule VM
poetry run ansible-playbook base.yml --limit enshrouded
```
Si une VM est recréée avec la même IP, supprimer l'ancienne empreinte SSH : `ssh-keygen -R <ip>`.

# Docker sur les VMs cloud-init
Le playbook `docker.yml` installe Docker (dépôt officiel, plugin compose) sur les VMs **démarrées** portant
les tags Proxmox `base` **et** `docker`. Lancer `base.yml` avant.
L'utilisateur SSH (`ansible_user`) est ajouté au groupe `docker`.

```bash
poetry run ansible-playbook docker.yml
poetry run ansible-playbook docker.yml --limit enshrouded
```

# Serveurs de jeu (Docker compose, sans unité systemd)
Chaque jeu a son rôle et son playbook, qui installe aussi Docker. La stack est lancée par le module
`community.docker.docker_compose_v2` (ne recrée que ce qui a changé), et redémarre au boot grâce à
`restart: unless-stopped`. Les fichiers sont dans `/opt/<jeu>` sur la VM (`docker compose ps` / `logs -f` depuis ce dossier).

## Enshrouded
VM taguée `enshrouded` (+ `base`). Image `sknnr/enshrouded-dedicated-server` (Proton), le jeu est mis à jour
par steamcmd à chaque démarrage du conteneur. La configuration (`enshrouded_server.json`) est générée par Ansible
depuis les variables `enshrouded_*` (voir `roles/enshrouded/defaults/main.yml`), la sauvegarde est dans `/opt/enshrouded/savegame`.

Les mots de passe sont dans un vault dédié (identité `enshrouded`), à créer une fois :
```bash
openssl rand -base64 32 > ~/.ansible_vault_credentials/.ansible_vault_enshrouded.pass && chmod 600 ~/.ansible_vault_credentials/.ansible_vault_enshrouded.pass
```
Ajouter `enshrouded@~/.ansible_vault_credentials/.ansible_vault_enshrouded.pass` à `vault_identity_list` dans `ansible.cfg`, puis :
```bash
mkdir -p inventories/group_vars/group_enshrouded
poetry run ansible-vault create inventories/group_vars/group_enshrouded/vault.yml --encrypt-vault-id enshrouded
```
```yaml
enshrouded_admin_password: <mot de passe admin>
enshrouded_friend_password: <mot de passe joueurs>
```
```bash
poetry run ansible-playbook enshrouded.yml
```
Ports à rediriger sur la box vers la VM : `15637/udp` (et `27015/udp`).

Sauvegarde du monde : archive toutes les 6 h, récupérée par le Proxmox principal (7 jours de rétention), playbook
`backup.yml`. Mise en place et restauration : [roles/savegame_backup/README.md](roles/savegame_backup/README.md).

## Assetto Corsa (AssettoServer, freeroam)
Guide complet (installation PC, mods, preset Shutoko, trafic, admin) : [roles/assetto/README.md](roles/assetto/README.md).

VM taguée `assetto` (+ `base`). Image `compujuckel/assettoserver:0.0.54`.
La configuration est versionnée dans le rôle (`roles/assetto/files/cfg/`, `templates/cfg/server_cfg.ini.j2`),
les mots de passe dans le vault `inventories/group_vars/group_assetto/vault.yml` (identité `assetto`).
Le contenu du jeu (`content/`, `system/`, issus du **Pack** de Content Manager) reste hors de git, dans `~/assetto-preset`
côté WSL (ou surcharger `assetto_content_dir`).

Le playbook envoie le contenu (rsync, sans suppression), dépose la configuration et recrée le conteneur si besoin :
```bash
poetry run ansible-playbook assetto.yml
```
Le conteneur est en réseau `host` : les ports sont ceux de `server_cfg.ini`. Ports à rediriger par défaut :
`9600/tcp`, `9600/udp`, `8081/tcp`.

## BeamNG.drive (BeamMP, freeroam)
VM taguée `beammp` (+ `base`). Binaire officiel BeamMP-Server installé comme service systemd, AuthKey dans le vault
`inventories/group_vars/group_beammp/vault.yml`. Guide complet (PC des joueurs, AuthKey, réglages, mods, ports) :
[roles/beammp/README.md](roles/beammp/README.md).
```bash
poetry run ansible-playbook beammp.yml
```

# Edit a secret vault
```bash
poetry run ansible-vault edit inventories/group_vars/all/proxmox.yaml
```
# Create a vault id
```bash
poetry run ansible-vault create vault.yml --encrypt-vault-id vault_id
```

# Edit a vault id
```bash
poetry run ansible-vault edit vault.yml --vault-id pki@~/.ansible_vault_credentials/.ansible_vault_pki.pass
```
The identity need to be added to the ansible.cfg to automate password resolution

```ini
[defaults]
vault_identity_list = pki@~/.ansible_vault_credentials/.ansible_vault_pki.pass
```

# Decrypting a crt
```bash
openssl x509 -in /tmp/ansible.jwp4vv5y/cert.crt -text -noout
```

# Generating hashed password (for the traefik dashboard)
Install apache2-utils
```bash
sudo apt install apache2-utils
```

Run the command
```bash
htpasswd -nb user password
```

# Connect to qbittorrent via curl
```bash
curl -v -i -X POST -d "username=login&password=password" "https:/qbittorrent.machiki.fr:444/api/v2/auth/login"
```
