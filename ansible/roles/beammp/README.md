# Serveur BeamNG.drive multijoueur (BeamMP)

Ce rôle déploie [BeamMP-Server](https://github.com/BeamMP/BeamMP-Server) **v3.9.3** (dernière version stable), le
serveur du mod multijoueur communautaire de BeamNG.drive, sur la VM taguée `beammp`. Le mode de base de BeamMP est le
**freeroam** : tout le monde roule ensemble sur la même map, sans course imposée.

Le serveur est installé directement depuis le binaire officiel (pas de Docker : BeamMP ne publie pas d'image officielle) :

```
/opt/beammp/
├── bin/BeamMP-Server-v3.9.3   binaire officiel Debian 13, vérifié par son SHA-256
├── beammp.env                 réglages + AuthKey (root, 0600), générés par Ansible
└── server/                    dossier de travail (utilisateur système beammp)
    ├── Server.log
    └── Resources/{Client,Server}/   mods
```

Il tourne comme service systemd `beammp` (démarrage au boot, relance en cas de crash), sous un utilisateur dédié sans droits.

**Pas de `ServerConfig.toml`** : le serveur réécrit ce fichier à chaque démarrage (AuthKey comprise), Ansible le
verrait donc toujours modifié. Les réglages passent par les variables `BEAMMP_*` du fichier `beammp.env`
(mode prévu par le serveur : `BEAMMP_PROVIDER_DISABLE_CONFIG`). Tout se règle avec les variables `beammp_*` du rôle.

---

## 1. Sur le PC de chaque joueur

| Quoi | Où | Remarques |
|---|---|---|
| **BeamNG.drive** | Steam | Chaque joueur doit posséder le jeu. |
| **Launcher BeamMP** | [beammp.com](https://beammp.com) | Lance BeamNG en mode multijoueur et télécharge automatiquement les mods du serveur à la connexion. Gratuit, demande un compte BeamMP (ou le mode invité). |

Les mods du serveur (maps, véhicules) sont téléchargés tout seuls par le launcher : rien d'autre à installer.

## 2. Sur le serveur

1. Créer la VM depuis le template 9000 (Full clone), **tags `base` et `beammp`**, IP fixe dans Cloud-Init.
   BeamMP est très léger (environ 50 Mo de RAM, pas de GPU) : 1 à 2 vCPU, 1 à 2 Go de RAM et le disque du template
   suffisent, à agrandir seulement si tu ajoutes beaucoup de mods.
2. Démarrer la VM, accepter l'empreinte SSH une fois (`ssh machiki@<ip>`), puis :
   ```bash
   poetry run ansible-playbook base.yml --limit beammp
   ```
3. Créer l'AuthKey et le vault (section 3), puis :
   ```bash
   poetry run ansible-playbook beammp.yml
   ```

## 3. AuthKey et vault

Tout serveur BeamMP a besoin d'une **AuthKey** (36 caractères), même privé : sans elle, il refuse de démarrer.

1. Se connecter sur le [Keymaster BeamMP](https://keymaster.beammp.com) avec son compte BeamMP et créer une clé.
2. Créer le vault-id `beammp`, une seule fois (depuis WSL) :
   ```bash
   openssl rand -base64 32 > ~/.ansible_vault_credentials/.ansible_vault_beammp.pass && chmod 600 ~/.ansible_vault_credentials/.ansible_vault_beammp.pass
   ```
   puis ajouter `beammp@~/.ansible_vault_credentials/.ansible_vault_beammp.pass` à `vault_identity_list` dans
   `ansible.cfg` (après avoir créé le fichier : un fichier de mot de passe absent bloque toutes les commandes Ansible).
3. Créer le vault, depuis `ansible/` :
   ```bash
   mkdir -p inventories/group_vars/group_beammp && poetry run ansible-vault create inventories/group_vars/group_beammp/vault.yml --encrypt-vault-id beammp
   ```
   ```yaml
   beammp_auth_key: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
   ```

Le dépôt GitHub est public : l'AuthKey ne doit jamais être ailleurs que dans ce vault.

## 4. Réglages

À surcharger dans `inventories/group_vars/group_beammp/main.yml` (fichier non chiffré, à créer) plutôt que dans le rôle :

| Variable | Défaut | Rôle |
|---|---|---|
| `beammp_name` | `Mordeci BeamMP` | Nom du serveur (codes couleur BeamMP acceptés : `^1`, `^l`...) |
| `beammp_description` | `Freeroam entre amis` | Description dans la liste des serveurs |
| `beammp_map` | `/levels/west_coast_usa/info.json` | Map, format `/levels/<map>/info.json` (voir plus bas) |
| `beammp_max_players` | `8` | Joueurs simultanés |
| `beammp_max_cars` | `2` | Véhicules par joueur en même temps |
| `beammp_private` | `true` | Caché de la liste publique : on rejoint par IP |
| `beammp_allow_guests` | `true` | Autoriser les joueurs sans compte BeamMP |
| `beammp_port` | `30814` | Port TCP + UDP |
| `beammp_tags` | `Freeroam` | Tags de recherche, séparés par des virgules |
| `beammp_log_chat` | `true` | Écrire le chat dans `Server.log` |
| `beammp_version` / `beammp_checksum` | `v3.9.3` / SHA-256 | Version du serveur : changer les deux ensemble (le SHA-256 est affiché sur la page de la release GitHub) |
| `beammp_resources_dir` | `~/beammp-resources` (WSL) | Dossier des mods à envoyer |

Exemple :
```yaml
beammp_name: "^4Mordeci ^rBeamMP"
beammp_map: /levels/italy/info.json
beammp_max_cars: 3
```

Maps fournies avec le jeu (nom du dossier dans `/levels/`), par exemple : `west_coast_usa`, `east_coast_usa`, `italy`,
`utah`, `jungle_rock_island`, `johnson_valley`, `industrial`, `small_island`, `hirochi_raceway`, `gridmap_v2`.
La liste complète est dans la [documentation BeamMP](https://docs.beammp.com/server/server-maintenance/).

Après modification : `poetry run ansible-playbook beammp.yml`. Le serveur ne redémarre que si quelque chose a changé
(nouveaux réglages, nouvelle version, mods modifiés).

## 5. Mods (maps et véhicules)

Les mods ne sont jamais dans git (contenu tiers, dépôt public). Côté WSL :
```
~/beammp-resources/
├── Client/   les .zip des mods (maps, véhicules) : envoyés aux joueurs à la connexion
└── Server/   plugins Lua du serveur (un dossier par plugin)
```
```bash
mkdir -p ~/beammp-resources/Client ~/beammp-resources/Server
```
Copier les `.zip` dans `Client/`, puis relancer `beammp.yml` : le dossier est synchronisé sur la VM et le serveur redémarre.
Pour une **map moddée**, mettre son zip dans `Client/` et régler `beammp_map` sur `/levels/<dossier de la map>/info.json`
(le nom du dossier se trouve dans le zip, sous `levels/`).

La synchronisation ne supprime rien : pour retirer un mod, le supprimer aussi sur la VM
(`/opt/beammp/server/Resources/Client/`), sinon les joueurs continueront de le télécharger.

## 6. Se connecter

- **En local** : dans le launcher BeamMP, onglet *Direct Connect*, IP de la VM et port `30814`. Rien à ouvrir sur la box.
- **Depuis l'extérieur** : rediriger sur la Freebox **`30814/tcp` et `30814/udp`** vers l'IP de la VM
  (*Paramètres de la Freebox* → *Mode avancé* → *Gestion des ports*), puis donner ton IP publique à tes amis.
  Pour apparaître dans la liste publique, passer `beammp_private: false`.

## 7. Administration

BeamMP n'a pas de rôle « admin » en jeu par défaut : la modération se fait par la console du serveur ou par un plugin
Lua serveur (des plugins communautaires ajoutent kick/ban et commandes d'admin dans le chat, à mettre dans
`~/beammp-resources/Server/` ; vérifier leur compatibilité avec la version du serveur).

Sous systemd, la console interactive n'est pas disponible. Pour surveiller le serveur, en SSH sur la VM :
```bash
sudo journalctl -u beammp -f
```
```bash
sudo systemctl restart beammp
```
`Server.log` (dans `/opt/beammp/server/`) contient la même chose ; d'après la documentation BeamMP, il n'affiche jamais l'AuthKey.

## 8. Pièges courants

- **Le service redémarre en boucle** : `journalctl -u beammp` ; le plus fréquent est une AuthKey absente ou invalide
  (« No AuthKey specified » ou clé de la mauvaise longueur).
- **Mise à jour** : le serveur affiche un message quand une nouvelle version sort. Changer `beammp_version` **et**
  `beammp_checksum`, puis relancer le playbook (le nouveau binaire est téléchargé à côté de l'ancien).
- **Les joueurs n'ont pas la map moddée** : vérifier que son zip est bien dans `Resources/Client/` sur la VM.
