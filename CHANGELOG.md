# Changelog

## v1.0.0 — première version
Launcher desktop type CurseForge pour le serveur Ebonhold : installe et met à jour
en un clic les addons et patches, au bon endroit dans l'installation WoW.

### Catalogue & installation
- **Catalogue** des mods avec cartes, badges (Installer / Mettre à jour / À jour), bannière
  « nouvelle version », barre de progression et notifications.
- **Installation** : téléchargement, **vérification SHA256**, extraction des addons dans
  `Interface\AddOns`, copie des patches dans `Data`, avec **sauvegarde + rollback** en cas d'erreur.
- **Recherche** et **filtres par catégorie** (catégories pilotées par le manifeste).
- **Packs / presets** : installer plusieurs mods en un clic (ex. « Pack FR complet »).
- **Désinstallation** (avec confirmation) et **réparation** des mods aux fichiers manquants.
- **Fiche détaillée** d'un mod : description longue + historique des versions.

### Outils & confort
- Barre du haut : **Vérifier**, **Tout mettre à jour**, **Jouer** (lance `Wow.exe`).
- Onglets **Installés**, **Nouveautés**, **Liens utiles** (Discord, Soul Tree, Guides).
- **Configuration langue FR** intégrée (remplace l'ancien `EbonholdFR-Installer`) : Jeu / Voix /
  Sorts / Réputations, avec journal en direct. Outils embarqués → aucune dépendance externe.

### Technique
- **Auto-update** du launcher : détection de version + téléchargement et remplacement automatique
  de l'exécutable.
- Ajout de mods **sans toucher au code** : tout passe par `manifest.json` (script `add_mod.py`).
- Stack : Python + pywebview + HTML/CSS/JS, packagé en `.exe` via PyInstaller.
