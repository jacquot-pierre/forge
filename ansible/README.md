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

# Edit a secret vault
```bash
poetry run ansible-vault edit inventories/group_vars/all/proxmox.yaml
```

# Create a vault id
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