# Changelog

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
