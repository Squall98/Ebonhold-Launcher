# Changelog

## v1.0.3 — correction de la lenteur au démarrage (proxy/réseau)
- WebView2 attendait l'expiration d'un timeout réseau au lancement (tentatives de
  proxy / services de fond) → plusieurs minutes d'attente. Le moteur est désormais
  forcé en **connexion directe** avec le **trafic réseau de fond coupé** → démarrage rapide.

## v1.0.2 — démarrage WebView2 plus rapide et fiable
- **Connexion au pont js↔Python sondée activement** (au lieu d'attendre un événement
  lent) → l'interface se peuple dès que le moteur est prêt, plus de longue attente
  « Ne répond pas ».
- **Profil WebView2 persistant** + **serveur local interne** → démarrages plus rapides et stables.
- Indicateur « Chargement du catalogue… » pendant l'initialisation.

## v1.0.1 — démarrage instantané
- **Démarrage instantané** : le catalogue local s'affiche immédiatement (plus de gel
  « Ne répond pas » au lancement). La vérification des nouveautés en ligne se fait
  désormais en arrière-plan, sans bloquer la fenêtre.
- Clarification de la traduction FR : distinction addon (contenu custom) / Patch FR (jeu de base).
- Base pour l'installation automatique du pack frFR (activable via le manifeste).

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
