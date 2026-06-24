# Changelog

## v1.0.5 — déblocage automatique des fichiers téléchargés
- **Déblocage automatique au démarrage** : le launcher retire lui-même la marque « fichier
  venu d'Internet » de ses fichiers. Corrige le crash au lancement
  (`Failed to resolve Python.Runtime.Loader.Initialize`) sur les PC où l'app a été téléchargée
  — plus besoin de « débloquer » le zip à la main.

## v1.0.4 — addons à plusieurs dossiers
- **Prise en charge des addons à plusieurs dossiers** (ex. GatherMate + GatherMate_Data) :
  installation **et désinstallation** propres de tous les dossiers (avant, la désinstallation
  ne retirait que le dossier principal).
- Nouveaux addons au catalogue : **Ackis Recipe List** et **GatherMate**.

## v1.0.3 — démarrage plus robuste + interface
- **Démarrage non bloquant** : la recherche du dossier Ebonhold se fait désormais en
  arrière-plan. Un disque lent ou déconnecté ne peut plus figer le launcher sur
  « Chargement du catalogue… ».
- **Interface rafraîchie après mise à jour** : le launcher vide son cache d'affichage
  quand sa version change (sinon l'ancienne interface restait servie en cache après un
  auto-update).
- **Catalogue** : barre de recherche et filtres répartis sur deux lignes (plus lisible).
- Nouveaux addons au catalogue : AutoCallboard, EbonBuilds, EbonClearance, Questie, Wardrobe.

## v1.0.2 — format dossier (fiabilité) + détection AppData
- **Distribution en dossier (zip)** au lieu d'un .exe unique : les fichiers ne sont plus
  ré-extraits dans `%TEMP%` à chaque lancement → corrige l'erreur **« Failed to load Python
  DLL »** causée par l'antivirus qui mettait en quarantaine l'extraction temporaire, et
  **démarrage plus rapide**.
- **Détection automatique** de l'install dans `%LOCALAPPDATA%\ebonhold` (emplacement par
  défaut du launcher officiel) — plus besoin de « Parcourir » pour la plupart des joueurs.
- Auto-update adapté au format dossier.

## v1.0.1 — correctif config FR (lecture seule)
- Corrige l'erreur « Permission denied » sur `Config.wtf` lors de l'application de la
  traduction : le fichier est souvent en **lecture seule** sur les serveurs privés
  (realmlist figé) → le launcher enlève désormais l'attribut avant d'écrire. Même
  correctif sur `realmlist.wtf`. Message plus clair si le jeu est encore ouvert.

## v1.0.0 — première version publique
Launcher desktop type CurseForge pour le serveur Ebonhold : installe et met à jour
en un clic les addons et la traduction, au bon endroit dans l'installation WoW.

### Catalogue & installation
- **Catalogue** des mods avec cartes, badges (Installer / Mettre à jour / À jour),
  bannière « nouvelle version », barre de progression et notifications.
- **Installation** : téléchargement, **vérification SHA256**, extraction des addons dans
  `Interface\AddOns`, avec **sauvegarde + rollback** en cas d'erreur.
- **Recherche** et **filtres par catégorie** (catégories pilotées par le manifeste).
- **Packs / presets**, **désinstallation** (avec confirmation), **réparation** des mods
  aux fichiers manquants, **fiche détaillée** (description + historique des versions).
- Chaque addon est téléchargé depuis **son propre dépôt GitHub** (source unique).

### Traduction française
- Onglet **Réglages** : configuration langue FR intégrée (Jeu / Voix / Sorts / Réputations),
  avec construction de `patch-Z.MPQ`, voix, locale et addon `EbonholdFRFix`.
- **Installation automatique du pack frFR** (~2,4 Go) : le launcher télécharge, vérifie,
  extrait et place le dossier `frFR` dans `Data`, sans intervention.

### Confort & technique
- Barre du haut : **Vérifier**, **Tout mettre à jour**, **Jouer** (lance `Wow.exe`).
- Onglets **Installés**, **Nouveautés**, **Liens utiles** (Discord, Soul Tree, Guides).
- **Démarrage instantané** (catalogue local affiché immédiatement, vérif en ligne en fond).
- **Auto-update** du launcher.
- Ajout de mods **sans toucher au code** (`manifest.json` + `add_mod.py`).
- Stack : Python + pywebview + HTML/CSS/JS, packagé en `.exe` (PyInstaller, icônes embarquées).
