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

exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="EbonholdLauncher",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                  # UPX = gros declencheur de faux positifs antivirus -> desactive
    runtime_tmpdir=None,
    console=False,              # appli fenetree (pas de console)
    icon="assets/icon.ico",
    version="version_info.txt",  # metadonnees (nom/editeur/version) -> moins suspect
)
