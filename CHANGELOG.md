# Changelog

## v1.0.11 — fiabilité et sécurité
- **Catalogue** : après une installation, le launcher ne revient plus à son catalogue
  embarqué (plus ancien). Le dernier catalogue en ligne est gardé sur le disque et sert
  au démarrage et hors ligne (« Catalogue (hors ligne) »).
- **« Tout mettre à jour »** ne met à jour que ce qui est déjà installé (avant : il
  installait tout le catalogue). Les installations passent une par une.
- **Numéros de version** : `1.1.6-fr1` n'est plus lu comme 1.1.61 (une 1.1.7 est bien vue
  comme plus récente).
- **Auto-mise à jour** : seul le dossier `_internal` du launcher est remplacé ; les autres
  fichiers du dossier où il est posé (Bureau, Téléchargements…) ne sont plus jamais
  supprimés. L'empreinte SHA256 est obligatoire. Plus de notification à chaque paquet.
- **Sécurité** : le texte des addons tiers (notes de version…) ne peut plus injecter de
  code dans le launcher ; seuls les liens web des sites connus s'ouvrent.
- **Installation des addons** : seuls les dossiers déclarés de l'addon sont extraits
  (jamais `ProjectEbonhold`, `Blizzard_*` ou un autre addon glissé dans le zip) ; nouvel
  essai automatique si la connexion coupe.
- **Pack FR** : le téléchargement de 2,6 Go reprend là où il s'est arrêté si la
  connexion coupe, la place libre est vérifiée avant, l'extraction se fait directement
  dans le jeu (moitié moins de place en temporaire).
- **Patch FR** : chaque fichier est lu dans le patch serveur le plus prioritaire (celui
  que le jeu utilise vraiment), avec un lecteur MPQ plus robuste. Le launcher refuse de
  toucher aux fichiers pendant que le jeu tourne. Correctif « double colonne » et
  +6 descriptions du 11/09 enfin livrés, **+5 traductions** (Unstable Infusion, montures).
- Exe plus léger (34 Mo au lieu de 48) ; tests automatiques (`tests/`).

## v1.0.10 — traduction FR à jour (nouvelle MAJ serveur)
- Traduction FR embarquée mise à jour : **+205 noms & +296 descriptions** custom traduits
  (echoes, arbre de compétences, affixes de gravure) → **2060 noms + 2718 descriptions**.
- Après auto-mise à jour du launcher, il suffit de **réappliquer le patch FR** (Réglages →
  Traduction) pour reconstruire `patch-Z` avec les nouvelles traductions.

## v1.0.8 — pack FR téléchargé depuis GitHub (même hors-ligne)
- Le **manifeste embarqué** (celui utilisé quand le launcher ne joint pas le catalogue
  en ligne, mode « Catalogue local ») pointait encore vers l'ancien lien **Google Drive**
  pour le pack FR → téléchargements **bloqués à 0 %** ou **« archive corrompue »** dès que
  le quota Drive était atteint. Le pack est désormais récupéré depuis **GitHub** (en deux
  parties, sans quota), y compris quand le launcher est en mode hors-ligne. Plus besoin
  d'installation manuelle du pack.

## v1.0.7 — détection des addons déjà installés
- Le launcher **détecte les addons déjà présents** dans `Interface\AddOns` (posés à la main)
  et les affiche comme **Installé** au lieu de « Installer », en lisant leur version sur le disque.

## v1.0.6 — affichages du catalogue
- **Bouton de bascule** en haut du catalogue : vue **Cartes**, **Liste compacte** ou
  **Tableau** (triable par colonne). Le choix d'affichage est mémorisé.

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
