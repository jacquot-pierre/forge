# Serveur Assetto Corsa freeroam (AssettoServer)

Ce rôle déploie [AssettoServer](https://assettoserver.org) **0.0.54**, la dernière version stable (celle que documente
le site), en serveur freeroam avec trafic IA, dans Docker sur la VM taguée `assetto`. Objectif de départ : la map **Shutoko Revival Project (SRP)**, l'autoroute de Tokyo, avec du trafic.

Principe : **la configuration du serveur se fait dans Content Manager sur ton PC** (c'est l'outil standard
d'Assetto Corsa), tu l'exportes avec « Pack » dans un dossier côté WSL, et Ansible l'envoie sur la VM puis lance le conteneur.
Ce dossier (le « preset ») n'est pas dans git : il contient le mot de passe admin et le contenu du jeu.

```
PC Windows                          WSL                              VM assetto (192.168.1.x)
Content Manager ── Pack ──>  ~/assetto-preset/  ── ansible ──>  /opt/assetto/data/  ──>  conteneur AssettoServer
                              cfg/ + content/      (rsync)        (monté dans /data)
```

---

## 1. Sur ton PC (et celui de chaque joueur)

| Quoi | Où | Remarques |
|---|---|---|
| **Assetto Corsa** | Steam | Le jeu de base suffit pour démarrer. |
| **Content Manager** | [acstuff.club/app](https://acstuff.club/app/) | Lanceur indispensable. L'onglet *Server* (création et Pack du preset) n'existe que dans la version **complète** (clé reçue par mail après un don, à saisir via le lien rouge *Switch to full version* en haut à droite) ; les joueurs peuvent se contenter de la version Lite gratuite. |
| **Custom Shaders Patch (CSP)** | Dans Content Manager : *Settings → Custom Shaders Patch* | **Obligatoire en pratique** : SRP, le trafic et la météo en dépendent ; l'authentification Steam demande CSP 0.1.75+, WeatherFX 0.1.76+, les messages client 0.1.77+. AssettoServer 0.0.54 n'impose pas de version minimale (le guide officiel décrit une astuce pour en exiger une). La pluie nécessite une version *preview* (Patreon de CSP). |
| **Shutoko Revival Project 0.9.3** | [shutokorevivalproject.com](https://shutokorevivalproject.com/#download) | Version stable actuelle (la 0.9.1 n'est plus supportée). Installer l'archive en la glissant dans Content Manager. Le dossier installé s'appelle `shuto_revival_project_beta`. |
| **SRP Car Pack** (facultatif) | [SRP_Car_Pack_3.6.7z](https://files.shutokorevivalproject.com/SRP_Car_Pack_3.6.7z) | Les voitures des serveurs officiels SRP. Inutile pour démarrer si tu n'utilises que des voitures Kunos (voir plus bas). |

> **Règle d'or** : chaque joueur doit avoir **exactement le même contenu** que le serveur (même version de SRP,
> mêmes voitures, y compris celles du trafic). Sinon : erreur de checksum à la connexion.

Pour démarrer simplement, utilise **uniquement des voitures Kunos** (fournies avec le jeu), y compris pour le trafic :
tes amis n'auront alors à installer que CSP et SRP.

## 2. Sur le serveur

Rien à installer à la main, Ansible s'occupe de tout :

1. Créer la VM depuis le template 9000 (Full clone), **tags `base` et `assetto`**, IP fixe dans Cloud-Init.
   AssettoServer est léger : 2 vCPU et 2 à 4 Go de RAM suffisent pour quelques joueurs (le trafic IA consomme surtout du CPU).
   Le preset « packé » ne contient que les données utiles au serveur (pas les modèles 3D) : +10 Go de disque suffisent.
2. Démarrer la VM, accepter l'empreinte SSH une fois (`ssh machiki@<ip>`), puis `poetry run ansible-playbook base.yml --limit assetto`.
3. Préparer le preset (section 3), puis `poetry run ansible-playbook assetto.yml` (installe aussi Docker).

## 3. Créer le preset SRP avec trafic

### 3.1 Dans Content Manager (onglet *Server*)

D'après le [guide officiel d'AssettoServer](https://assettoserver.org/docs/thebeginnersguide) :

1. Si l'onglet *Server* n'apparaît pas, l'activer dans les réglages de Content Manager. Créer un preset et le renommer.
2. **Main** :
   - **Track** : Shutoko Revival Project, layout **Main Layout**.
   - **Admin password** : au moins 8 caractères (c'est ton accès admin, voir section 4).
   - **Password** : facultatif, pour réserver le serveur à tes amis.
   - **Capacity** : nombre total de places, **joueurs + voitures IA**. Ne pas dépasser le nombre de stands (pits)
     indiqué sous le curseur : au-delà, les clients crashent en se connectant.
3. **Entry list** : d'abord les voitures des **joueurs**, ensuite celles du **trafic**. Exemple du guide pour 11 places :
   1 RUF CTR Yellowbird (joueur), puis 5 Audi S1 et 5 Toyota GT86 (trafic). Toutes des voitures Kunos.
   La *Capacity* doit correspondre au nombre de voitures de la liste.
4. **Rules** : décocher *Virtual mirror*, mettre *Allowed tyres out* sur *Any*.
5. **Conditions** : ne **pas** utiliser *WeatherFX Time*, *Time multiplier* ni *Date* (incompatibles avec AssettoServer).
6. **Sessions** : cocher *Pickup mode* et *Loop mode*, laisser *Locked entry list* décoché, décocher *Booking*,
   *Qualifying* et *Race*, garder seulement *Practice* (environ 2 h).
7. *Save*, puis **Pack** : décocher *Include executable* et *Pack into single exe-file* (l'exécutable vient de l'image Docker).

### 3.2 Extraire le pack côté WSL

```bash
mkdir -p ~/assetto-preset
```
Extraire l'archive du pack dedans, **sans dossier intermédiaire** : on doit avoir directement
`~/assetto-preset/cfg/` et `~/assetto-preset/content/`. Depuis WSL, l'archive Windows est sous `/mnt/c/Users/<toi>/...` :
```bash
cd ~/assetto-preset && unzip /mnt/c/Users/<toi>/Downloads/<preset>.zip
```
(Autre emplacement : surcharger `assetto_preset_dir`.)

### 3.3 Activer le trafic (fichiers du preset)

**`cfg/entry_list.ini`** : les voitures des joueurs gardent `AI=none`, celles du trafic passent en `AI=fixed` :
```ini
[CAR_0]
MODEL=ruf_yellowbird
AI=none
...
[CAR_1]
MODEL=ks_audi_a1s1
AI=fixed
...
```
Il faut **une entrée `AI=none` par joueur pouvant être connecté en même temps** : pour jouer à 4, prévoir au moins
4 voitures joueurs (identiques ou non) avant celles du trafic. Une entrée `AI=fixed` est réservée au trafic, aucun joueur ne peut la prendre.

**`cfg/server_cfg.ini`**, section `[PRACTICE]` : ajouter `INFINITE=1` (session sans fin ; Content Manager affichera quand même un temps restant).

**`cfg/extra_cfg.yml`** : à créer. AssettoServer en génère un complet (avec la description de chaque option) au
premier démarrage s'il n'existe pas. Les options absentes gardent leur valeur par défaut ; en 0.0.54, l'authentification
Steam, WeatherFX et les messages client sont **désactivés par défaut**. Ce minimum suffit :
```yaml
EnableAi: true
# Indispensable pour admins.txt / whitelist.txt (section 4)
UseSteamAuth: true
# Météo CSP (pluie, transitions) et panneaux contresens / phares (CSP requis)
EnableWeatherFx: true
EnableClientMessages: true
EnableServerDetails: true
ServerDescription: "Shutoko freeroam - Forge"
AiParams:
  # Vitesse de base du trafic (km/h), les voies de droite roulent plus vite (RightLaneOffsetKph)
  MaxSpeedKph: 80
  # Rayon autour des joueurs dans lequel le trafic est simulé
  PlayerRadiusMeters: 200
```
Le fichier YAML est **sensible à l'indentation** : 2 espaces, jamais de tabulation.

**La spline IA `fast_lane.aip`** : c'est le tracé que suit le trafic. Sans elle, le serveur s'arrête au démarrage
(« No ai folder found »). Elle doit se trouver dans
`content/tracks/shuto_revival_project_beta/ai/fast_lane.aip`. Vérifie si ton installation de SRP la contient déjà
(dossier `ai/` de la piste dans Assetto Corsa), sinon récupère-la sur le [Discord d'AssettoServer](https://discord.gg/uXEXRcSkyz)
ou celui de [SRP](https://discord.gg/shutokorevivalproject), et copie-la dans le preset (créer le dossier `ai`).

**Options CSP** (facultatif) : dans Content Manager, onglet *Entry list*, bouton *CSP* : autoriser la conduite à
contresens (`ALLOW_WRONG_WAY`), le changement de couleur partout, la vitesse dans les stands, des points de
téléportation SRP... C'est enregistré dans `cfg/csp_extra_options.ini`, à garder dans le preset.

**Météo et pluie** : nécessite `EnableWeatherFx: true` dans `extra_cfg.yml` côté serveur, et côté joueurs une version
de CSP qui gère la pluie (version *preview*, Patreon de CSP) : les autres joueurs restent au sec. Trois façons de faire :

- **Au démarrage** : dans `cfg/server_cfg.ini`, section `[WEATHER_0]`, mettre le type WeatherFX à la fin de `GRAPHICS` :
  ```ini
  GRAPHICS=3_clear_type=7
  ```
- **À chaud** (admin) : `/cspweather` liste les types, `/setcspweather <type> <transition en s>` en applique un.
- **Aléatoire** : le plugin `RandomWeatherPlugin` change de météo tout seul (voir l'exemple plus bas).

Types utiles (enum `WeatherFxType`) : `15` Clear, `16` FewClouds, `18` BrokenClouds, `19` OvercastClouds, `20` Fog,
`3`/`4`/`5` Light/Drizzle/HeavyDrizzle, `6`/`7`/`8` LightRain/Rain/HeavyRain, `0`/`1`/`2` Light/Thunderstorm/HeavyThunderstorm.

Météo aléatoire avec pluie, à ajouter **à la fin** de `extra_cfg.yml` (le `---` sépare la config du plugin) :
```yaml
EnablePlugins:
  - RandomWeatherPlugin
---
!RandomWeatherConfiguration
# Poids de tirage, 0 = jamais. Les types absents ont un poids de 1 : mettre 0 pour neige, sable, tornade...
WeatherWeights:
  Clear: 3
  FewClouds: 2
  OvercastClouds: 1
  LightRain: 1
  Rain: 1
  HeavyRain: 0.5
  Thunderstorm: 0.3
  LightSnow: 0
  Snow: 0
  HeavySnow: 0
  LightSleet: 0
  Sleet: 0
  HeavySleet: 0
  Sand: 0
  Dust: 0
  Smoke: 0
  Squalls: 0
  Tornado: 0
  Hurricane: 0
  Cold: 0
  Hot: 0
  Windy: 0
  Hail: 0
MinWeatherDurationMinutes: 15
MaxWeatherDurationMinutes: 60
MinTransitionDurationSeconds: 180
MaxTransitionDurationSeconds: 600
```
Si `EnablePlugins` existe déjà plus haut dans le fichier, y ajouter la ligne au lieu de le dupliquer.

### 3.4 Déployer

```bash
poetry run ansible-playbook assetto.yml
```
Le playbook vérifie que le preset est complet, l'envoie dans `/opt/assetto/data` (rsync, sans rien supprimer côté VM),
et recrée le conteneur si quelque chose a changé. Pour toute modification : éditer le preset, relancer la même commande.

Logs, en SSH sur la VM :
```bash
cd /opt/assetto && docker compose logs -f
```
`[ERR]` = erreur récupérable, `[FTL]` = erreur fatale (le serveur s'arrête et Docker le relance en boucle).

## 4. Être admin

Deux façons, cumulables :

- **Mot de passe** : en jeu, ouvrir le chat et taper `/admin <mot de passe admin>` (celui du preset, `ADMIN_PASSWORD` dans `server_cfg.ini`).
- **Automatique** : créer `~/assetto-preset/admins.txt` avec ton **SteamID64** (17 chiffres, visible sur ton profil
  Steam ou via steamid.io), un par ligne. AssettoServer te reconnaît à chaque connexion. Ça repose sur
  l'authentification Steam : **`UseSteamAuth: true` obligatoire** dans `extra_cfg.yml` (désactivée par défaut en 0.0.54).
  Sans elle, n'importe qui pourrait usurper ton SteamID, et le serveur refuse de démarrer avec un `admins.txt` non vide.

Sur le même principe : `whitelist.txt` (seuls ces SteamID peuvent se connecter) et `blacklist.txt` (bannis).

Commandes admin utiles ([liste complète](https://assettoserver.org/docs/admin-commands)) :

| Commande | Effet |
|---|---|
| `/settime 22:30` | Change l'heure (la nuit sur Shutoko, ça vaut le coup) |
| `/cspweather` puis `/setcspweather <type> <durée>` | Liste les météos CSP puis en applique une (transition en secondes) |
| `/kick <joueur>`, `/ban <joueur>` | Expulser, bannir |
| `/pit <joueur>` | Renvoyer un joueur aux stands |
| `/whois <joueur>` | IP et profil Steam d'un joueur |
| `/set Extra.<option> <valeur>` | Change une option de `extra_cfg.yml` à chaud (perdu au redémarrage) |

## 5. Se connecter

- **En local** : Content Manager → *Drive* → *Online* → **Favourites**, ajouter le serveur par `IP-de-la-VM:8081`
  (le port HTTP, `HTTP_PORT` dans `server_cfg.ini`), puis *Join*. Selon les versions de Content Manager, un onglet
  *LAN* peut aussi le détecter tout seul. Rien à ouvrir sur la box. Pour vérifier que le serveur répond, ouvrir
  `http://IP-de-la-VM:8081/INFO` dans un navigateur : il doit renvoyer un JSON avec le nom du serveur.
- **Depuis l'extérieur** : rediriger sur la Freebox vers la VM **`9600/tcp`, `9600/udp` et `8081/tcp`**
  (ports par défaut, définis dans `server_cfg.ini` : le conteneur est en réseau `host`). Sans ces redirections, le
  log affiche « INVALID SERVER, CHECK YOUR PORT FORWARDING SETTINGS » : sans importance pour jouer en local.
  Pour inviter quelqu'un, partager le lien d'invitation affiché dans les logs, pas le bouton *Invite* de Content Manager
  (qui donne une IP locale).

## 6. Pièges courants

- **Erreur de checksum** à la connexion : contenu différent entre le joueur et le serveur (version de SRP, voiture, skin).
- **Crash du client en rejoignant** : *Capacity* supérieure au nombre de stands de la piste.
- **Seules les premières voitures apparaissent** : *Capacity* inférieure au nombre de voitures de l'entry list.
- **Le serveur redémarre en boucle** : regarder la première ligne `[FTL]` des logs (spline absente, YAML mal indenté...).
- **`Failed to load module '/root/.steam/sdk64/steamclient.so'`** : n'arrive pas en 0.0.54. Depuis 0.0.55-pre44,
  l'image AssettoServer ne contient plus la bibliothèque Steam nécessaire à l'authentification Steam : pour ces
  versions, mettre `assetto_steamclient_from_steamcmd: true`, le rôle l'extrait alors de l'image `cm2network/steamcmd`
  dans `/opt/assetto/steam/` et la monte dans le conteneur (supprimer ce dossier pour la mettre à jour).
- **Mise à jour d'AssettoServer** (variable `assetto_image`) : des options peuvent être renommées. Garder une copie
  de son `extra_cfg.yml` et relire les notes de version avant de changer de version.

## Variables du rôle

| Variable | Défaut | Rôle |
|---|---|---|
| `assetto_preset_dir` | `~/assetto-preset` (côté WSL) | Dossier du preset à envoyer |
| `assetto_image` | `compujuckel/assettoserver:0.0.54` | Version d'AssettoServer (dernière stable ; les suivantes sont des pré-versions `0.0.55-preXX`) |
| `assetto_steamclient_from_steamcmd` | `false` | Fournir `steamclient.so` au conteneur, nécessaire à partir de `0.0.55-pre44` |
| `assetto_dir` | `/opt/assetto` | Dossier sur la VM |
| `assetto_timezone` | `Europe/Paris` | Fuseau du conteneur |
