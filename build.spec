# -*- mode: python ; coding: utf-8 -*-
"""Build PyInstaller du launcher Ebonhold -> un seul EbonholdLauncher.exe.

Lancer :  python -m PyInstaller build.spec --noconfirm
Sortie  :  dist/EbonholdLauncher.exe
"""
from PyInstaller.utils.hooks import collect_all

# pywebview embarque ses propres hooks PyInstaller, mais on force la collecte
# de ses sous-modules + de ceux du backend Windows (EdgeChromium via pythonnet).
datas, binaries, hiddenimports = [], [], []
for pkg in ("webview", "clr_loader", "proxy_tools", "bottle"):
    try:
        d, b, h = collect_all(pkg)
        datas += d; binaries += b; hiddenimports += h
    except Exception:
        pass

# Ressources de l'app (interface web, outils FR embarques, catalogue, icone).
datas += [
    ("web", "web"),
    ("vendor", "vendor"),
    ("manifest.json", "."),
    ("assets", "assets"),
]
# Cle du depot prive des signalements : fichier local, JAMAIS dans git (voir .gitignore).
# L'exe n'embarque qu'une copie au jeton MASQUE (core/secret.py), generee ici dans build/.
import json
import os
import sys
if os.path.isfile(os.path.join("secrets", "report.json")):
    sys.path.insert(0, os.path.abspath("core"))
    import secret as _secret
    with open(os.path.join("secrets", "report.json"), encoding="utf-8-sig") as _f:
        _cfg = json.load(_f)
    _jeton = str(_cfg.get("token") or "").strip()
    if _jeton:
        os.makedirs(os.path.join("build", "secrets"), exist_ok=True)
        with open(os.path.join("build", "secrets", "report.json"), "w", encoding="utf-8") as _f:
            json.dump({"repo": _cfg.get("repo", ""), "branch": _cfg.get("branch", ""),
                       "token_x": _secret.masquer(_jeton)}, _f)
        datas += [("build/secrets/report.json", "secrets")]
hiddenimports += ["mpyq", "clr"]

a = Analysis(
    ["main.py"],
    pathex=["vendor"],          # pour mpqwrite / dbc_localize embarques
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter"],       # non utilise par le launcher
    noarchive=False,
)
pyz = PYZ(a.pure)

# Build ONE-FOLDER (et non one-file) : les fichiers (python314.dll, runtime VC++, web/,
# vendor/...) sont poses une fois sur le disque au lieu d'etre re-extraits dans %TEMP% a
# chaque lancement -> plus de faux "Failed to load Python DLL" causes par l'antivirus qui
# met en quarantaine l'extraction temporaire, et demarrage plus rapide.
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,      # one-folder : les binaires vont dans COLLECT, pas dans l'exe
    name="EbonholdLauncher",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                  # UPX = gros declencheur de faux positifs antivirus -> desactive
    console=False,              # appli fenetree (pas de console)
    icon="assets/icon.ico",
    version="version_info.txt",  # metadonnees (nom/editeur/version) -> moins suspect
)

coll = COLLECT(
    exe, a.binaries, a.datas,
    strip=False,
    upx=False,
    name="EbonholdLauncher",    # -> dist/EbonholdLauncher/ (dossier a distribuer en .zip)
)
