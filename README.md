# Ebonhold Launcher

Launcher desktop type CurseForge pour le serveur Ebonhold : installe et met à jour
en un clic les addons (`EbonholdFR`, `EbonholdCheckpoints`) et le patch de données
custom, au bon endroit dans l'installation WoW du joueur.

---

### 👥 Pour l'équipe — ajouter un addon

- 🧩 **[Ajouter un addon (formulaire)](https://github.com/Squall98/Ebonhold-Launcher/issues/new?template=add-addon.yml)** — tu remplis un formulaire, un robot ouvre la Pull Request.
- 📖 **[Guide pas-à-pas](https://github.com/Squall98/Ebonhold-Launcher/issues/1)** (issue épinglée) — comment ça marche, en 2 minutes.
- 🛠️ **[CONTRIBUTING.md](CONTRIBUTING.md)** — la référence technique des champs et du flux.

> **Mettre à jour un addon** = publier une **Release** sur son dépôt : le catalogue se met à jour tout seul.

---

## Lancer en développement

```bash
cd launcher
python -m pip install -r requirements.txt
python main.py
```

La fenêtre charge `web/index.html` (UI HTML/CSS/JS) et expose l'API Python via pywebview.
Si le backend n'est pas là (ouverture du HTML seul dans un navigateur), un jeu de données
fictif (`MOCK` dans `app.js`) permet de visualiser l'interface.

## Architecture

```
launcher/
├── main.py              Point d'entrée : fenêtre pywebview + API
├── core/
│   ├── api.py           Classe Api exposée au JS (get_catalog, install_product, …)
│   ├── catalog.py       Récupère le manifest.json (en ligne, fallback local)
│   ├── installer.py     Download + SHA256 + extraction ZIP / copie MPQ + rollback
│   ├── state.py         État local : %APPDATA%\EbonholdLauncher\state.json
│   ├── wow.py           Détection du dossier WoW + chemins AddOns / Data
│   └── paths.py         Resources (PyInstaller) + dossier de données
├── web/                 index.html · style.css · app.js
└── manifest.json        Catalogue (DEV : URLs locales ; PROD : URLs GitHub Releases)
```

## Catalogue (manifest.json)

Le launcher lit un `manifest.json` central. En production il sera hébergé sur le repo
`Squall98/Ebonhold-Launcher` (branche `main`) et récupéré via :

```
https://raw.githubusercontent.com/Squall98/Ebonhold-Launcher/main/manifest.json
```

Chaque produit déclare `install_target` (`addons` → `Interface\AddOns`, `data` → `Data`),
sa `version`, son `download_url` et son `sha256` (vérification d'intégrité).

> La version livrée pointe vers des fichiers **locaux** (`V:/Project/Ebonhold/releases/…`)
> pour permettre le test hors-ligne. Pour publier : remplacer les `download_url` par les
> URLs des Releases GitHub et recalculer/garder les `sha256`.

## Ajouter / mettre à jour un mod (catalogue auto-généré)

Le catalogue (`manifest.json`) est **généré automatiquement** — personne n'édite ce fichier à la
main ni ne calcule de SHA256. Deux sources : `manifest-meta.json` (partie globale, admin) +
`catalog/*.toml` (une fiche par addon). Pour chaque fiche, la **dernière Release GitHub** du dépôt
indiqué fournit la `version`, le `download_url`, le `sha256` et l'historique.

- **Mettre à jour un addon** → publier une nouvelle **Release** sur son dépôt. Le catalogue se
  régénère tout seul (Action `build-manifest.yml` : sur changement de `catalog/`, toutes les 2 h,
  ou via le bouton *Run workflow*).
- **Ajouter un addon** → le [formulaire](https://github.com/Squall98/Ebonhold-Launcher/issues/new?template=add-addon.yml)
  (un robot ouvre la PR) ou créer une fiche `catalog/<id>.toml` (voir `catalog/_TEMPLATE.toml`).
  Tout est détaillé dans [CONTRIBUTING.md](CONTRIBUTING.md) et le [guide épinglé](https://github.com/Squall98/Ebonhold-Launcher/issues/1).

Régénérer / valider en local (admin) :

```bash
python tools/build_manifest.py            # régénère manifest.json depuis les sources
python tools/build_manifest.py --check    # montre le résultat sans rien écrire
python tools/build_manifest.py --only <id> --strict   # valide une seule fiche
```

> L'ancien `add_mod.py` (édition directe de `manifest.json`) reste utilisable en local mais n'est
> plus la méthode recommandée : la source du catalogue est désormais `catalog/*.toml`.

### Catégories et packs (pilotés par le manifeste)

- `categories` (dans `manifest-meta.json`) : filtres du catalogue. Seules celles **réellement
  utilisées** par un mod s'affichent (pas d'onglet vide).
- `packs` : presets installables en un clic (ex. « Pack FR complet » = plusieurs mods).

## État d'avancement

- [x] Cœur : détection WoW, catalogue, installeur (ZIP + MPQ), état local, rollback, checksum
- [x] UI catalogue : cartes, badges, bannière, barre de progression, toasts, **recherche + filtres**
- [x] Barre du haut : Vérifier, Tout mettre à jour, Jouer (lance Wow.exe)
- [x] **Désinstallation** (avec confirmation) ; **badge** de mises à jour dans la sidebar
- [x] Onglets Installés, Nouveautés (notes + changelogs), **Liens utiles** (Discord/Soul Tree/Guides)
- [x] Réglages → dossier WoW + **config langue FR autonome** (outils embarqués dans `vendor/`) + ouvrir AddOns
- [x] **Catégories data-driven** + **filtres** dynamiques depuis le manifeste
- [x] **Packs / presets** (installer plusieurs mods en un clic)
- [x] **Fiche détaillée** d'un mod (clic carte → description longue + historique des versions)
- [x] **Réparation** : détection des mods aux fichiers manquants → bouton « Réparer »
- [x] **Auto-update du launcher** : détection + téléchargement/remplacement auto du `.exe` (`core/selfupdate.py`) ; en dev, ouvre la page
- [x] **Packaging PyInstaller** (`build.spec`) → `EbonholdLauncher.exe`
- [x] **Publié** : repo public + release `v1.0.0` (exe + addons + patch-Z)

> **v1.0.0 en ligne** : [Ebonhold-Launcher](https://github.com/Squall98/Ebonhold-Launcher) ·
> [release v1.0.0](https://github.com/Squall98/Ebonhold-Launcher/releases/tag/v1.0.0).
> Le launcher lit le catalogue **en ligne** (`manifest.json`) : ajouter un mod/catégorie/pack ne nécessite
> aucun re-téléchargement côté joueur. Pour tester en local, `python main.py` utilise `manifest.dev.json`.

## Compiler l'exe

```bash
python -m PyInstaller build.spec --noconfirm
# -> dist/EbonholdLauncher/EbonholdLauncher.exe (+ _internal/)
```

## Compiler l'installeur (Inno Setup)

Nécessite [Inno Setup 6](https://jrsoftware.org/isdl.php) installé (`winget install JRSoftware.InnoSetup`).
`ISCC.exe` n'est pas ajouté au PATH par défaut : l'appeler par son chemin complet
(`%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe` ou `C:\Program Files (x86)\Inno Setup 6\ISCC.exe`
selon le mode d'installation), ou l'ajouter au PATH.

```bash
ISCC.exe installer.iss /DAppVersion=1.0.8
# -> dist_installer/EbonholdLauncherSetup.exe
```

Installation par utilisateur (pas d'admin/UAC), raccourci Menu Démarrer/Bureau, désinstalleur
listé dans « Applications installées ».

## Publier une mise à jour

- **Nouveau mod** : `python add_mod.py …` puis commit/push de `manifest.json` + uploader l'asset sur une release.
- **Nouvelle version du launcher** : bump `APP_VERSION` (`core/version.py`) et `launcher_version` du manifeste,
  recompiler l'exe et l'installeur, recalculer `launcher_sha256` à partir du **zip** de
  `dist/EbonholdLauncher/` (c'est ce zip que `core/selfupdate.py` télécharge pour l'auto-update).
  Créer une release GitHub avec deux assets : `EbonholdLauncherSetup.exe` (téléchargement manuel)
  et `EbonholdLauncher.zip` (auto-update).

## Traduction française (intégrée au launcher)

Deux choses complémentaires, toutes deux gérées dans le launcher :

- **Addon EbonholdFR** (catalogue) → contenu custom (echoes, arbre de talents, affixes, tomes).
- **Patch FR** (onglet Réglages) → jeu de base (sorts, hauts faits, titres, quêtes, menus).
  Reprend 100% de l'ancien `EbonholdFR-Installer.exe` (`core/frconfig.py` + `vendor/`) : build de
  `patch-Z.MPQ`, voix, locale, addon `EbonholdFRFix`. Plus besoin de l'exe séparé.

### Pack frFR (~2,4 Go, pour le français complet)

Le launcher peut **télécharger et installer le pack automatiquement** (`core/frpack.py`) : il place
le dossier `frFR/` dans `Data`. Pour l'activer, renseigne `fr_config.pack_download` dans le manifeste :

```json
"fr_config": {
  "pack_url": "https://…/page",            // lien manuel (fallback)
  "pack_note": "…",
  "pack_download": {                        // active le bouton « Installer le pack FR »
    "format": "zip",                        // zip recommandé (rar/7z best-effort via tar système)
    "url":   "https://…/frFR.zip"           // lien direct unique
    // —— OU, si > 2 Go (limite GitHub), découpé en parties réassemblées par le launcher : ——
    // "parts": ["https://…/frFR.zip.001", "https://…/frFR.zip.002"]
  }
}
```

Conseils : **re-empaqueter le pack en `.zip`** (extraction native fiable) ; comme un asset GitHub est
limité à 2 Go, soit héberger en lien direct unique ailleurs, soit **découper** le `.zip` en parties
< 2 Go (`split` / `copy /b`) et lister les URLs dans `parts`. Activer ne nécessite **pas** de recompiler
l'exe — c'est de la config en ligne.

## Dossier `vendor/` (config FR autonome)

Outils + données embarqués pour que la config FR fonctionne sans dépendance externe :
`mpqwrite.py`, `dbc_localize.py`, `custom_translations.json`, addon `EbonholdFRFix/`. Le module
pip `mpyq` reste requis (cf `requirements.txt`).
