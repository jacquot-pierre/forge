# forge-ansible
Ansible Forge to deploy infrastructure

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
| gaming | 192.168.1.125:8006 | `inventory_lxc.proxmox_gaming.yaml`, `inventory_qemu.proxmox_gaming.yaml` |

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
mise à jour, paquets de base, qemu-guest-agent, fuseau horaire, mises à jour de sécurité automatiques, TRIM, durcissement SSH.

Il cible les VMs **démarrées** portant le tag Proxmox `base` (groupe `group_base`), sur les deux serveurs.
Mettre le tag `base` sur le template : chaque clone en hérite.

Prérequis sur la VM : IP fixe dans l'onglet Cloud-Init (`ipconfig0`), utilisateur `debian` avec ta clé SSH
(sinon surcharger `ansible_user`).

```bash
# Toutes les VMs "base" démarrées
poetry run ansible-playbook base.yml
# Une seule VM
poetry run ansible-playbook base.yml --limit enshrouded
```
Si une VM est recréée avec la même IP, supprimer l'ancienne empreinte SSH : `ssh-keygen -R <ip>`.

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
