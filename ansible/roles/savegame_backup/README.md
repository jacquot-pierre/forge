# Sauvegarde des mondes de jeu (Enshrouded)

Deux rôles, lancés ensemble par le playbook `backup.yml` :

| Rôle | Où | Ce qu'il fait |
|---|---|---|
| `savegame_backup` | VM Enshrouded | Toutes les **6 h** (0h, 6h, 12h, 18h), archive `/opt/enshrouded/savegame` dans `/var/backups/savegames/enshrouded-AAAAMMJJ-HHMM.tar.gz` |
| `backup_pull` | Proxmox principal (192.168.1.70) | 15 min plus tard, **récupère** les archives dans `/srv/backups/savegames/enshrouded/` |

Rétention, des deux côtés : les archives de plus de **7 jours** sont supprimées, mais les **28 plus récentes** sont
toujours gardées (7 jours × 4 par jour). Comme la VM est souvent éteinte plusieurs jours, ça évite de tout perdre
au retour : sans nouvelle archive, rien n'est supprimé.

```
VM enshrouded (192.168.1.210)                         Proxmox principal (192.168.1.70)
/opt/enshrouded/savegame                              /srv/backups/savegames/enshrouded/
   │ timer toutes les 6 h (tar.gz)                       ▲
   ▼                                                     │ timer +15 min : rsync en lecture seule
/var/backups/savegames/ ──── utilisateur savegame-backup ┘ (clé SSH du Proxmox, limitée à ce dossier)
```

**Pourquoi c'est le Proxmox qui vient chercher** (« pull ») : la VM de jeu est exposée sur Internet. Si elle était
compromise, elle ne doit avoir aucun accès à l'hyperviseur. Ici, c'est l'inverse : le Proxmox a une clé SSH qui ne
permet, sur la VM, que de **lire** le dossier des archives (`rrsync -ro`, commande forcée), rien d'autre.

- Si la VM est éteinte au moment de la récupération, le Proxmox passe son tour (« unreachable, skipped ») sans erreur.
- Une archive manquée parce que la VM était éteinte est faite à son prochain démarrage (timer `Persistent`).

---

## 1. Prérequis (une seule fois) : accès SSH au Proxmox principal

Ansible doit pouvoir se connecter en root au Proxmox principal. Depuis WSL :
```bash
ssh-copy-id root@192.168.1.70
```
Accepter l'empreinte (`yes`) puis saisir le mot de passe root du Proxmox. Vérifier ensuite :
```bash
ssh root@192.168.1.70 hostname
```
L'adresse est déclarée dans `inventories/host_vars/proxmox.yaml`.

## 2. Déployer

La VM Enshrouded doit être **démarrée**. Depuis `ansible/` :
```bash
poetry run ansible-playbook backup.yml
```
Toujours lancer le playbook **en entier** (pas de `--limit`) : la partie VM a besoin de la clé publique lue sur le Proxmox.
Si la VM Enshrouded est recréée, relancer `backup.yml` (le nouvel utilisateur et la nouvelle clé d'hôte sont gérés).

## 3. Vérifier

Sur la VM :
```bash
systemctl list-timers 'savegame-backup-*'
```
```bash
sudo ls -lh /var/backups/savegames/
```
Forcer une archive tout de suite : `sudo systemctl start savegame-backup-enshrouded`

Sur le Proxmox principal :
```bash
systemctl list-timers backup-pull.timer
```
```bash
ls -lh /srv/backups/savegames/enshrouded/
```
Forcer une récupération : `systemctl start backup-pull`, puis `journalctl -u backup-pull -n 20`.

## 4. Restaurer un monde

1. Choisir l'archive sur le Proxmox :
   ```bash
   ssh root@192.168.1.70 ls -lh /srv/backups/savegames/enshrouded/
   ```
2. La copier sur la VM (depuis WSL, `-3` fait transiter la copie par ton PC) :
   ```bash
   scp -3 root@192.168.1.70:/srv/backups/savegames/enshrouded/enshrouded-AAAAMMJJ-HHMM.tar.gz machiki@192.168.1.210:/tmp/
   ```
3. Sur la VM, arrêter le serveur, mettre l'ancien monde de côté, extraire, remettre les droits, redémarrer :
   ```bash
   cd /opt/enshrouded && docker compose stop
   ```
   ```bash
   sudo mv savegame savegame.avant-restauration && sudo tar -C /opt/enshrouded -xzf /tmp/enshrouded-AAAAMMJJ-HHMM.tar.gz && sudo chown -R 10000:10000 savegame
   ```
   ```bash
   docker compose start && docker compose logs -f
   ```
Une fois le monde vérifié en jeu : `sudo rm -rf /opt/enshrouded/savegame.avant-restauration`.

## 5. Réglages

| Variable | Défaut | Rôle |
|---|---|---|
| `savegame_backup_schedule` / `backup_pull_schedule` | `00/6:00` / `00/6:15` | Fréquence (format systemd `OnCalendar`) |
| `savegame_backup_keep_days` / `backup_pull_keep_days` | `7` | Âge maximal des archives |
| `savegame_backup_keep_min` / `backup_pull_keep_min` | `28` | Nombre d'archives toujours gardées |
| `savegame_backup_dir` | `/var/backups/savegames` | Archives sur la VM |
| `backup_pull_dir` | `/srv/backups/savegames` | Archives sur le Proxmox principal |

Limite à garder en tête : les deux copies sont chez toi. Elles protègent d'une panne du serveur gaming ou d'une
erreur de manipulation, pas d'un sinistre (incendie, vol) qui toucherait les deux machines.
