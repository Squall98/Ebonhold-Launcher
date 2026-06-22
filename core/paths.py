# -*- coding: utf-8 -*-
"""Chemins de l'application : resources embarquees (PyInstaller) et dossier de donnees utilisateur."""
import os
import sys


def resource(rel):
    """Chemin vers une resource embarquee (web/, assets/, manifest.json...).

    En mode PyInstaller one-file, les resources sont depaquetees dans sys._MEIPASS.
    En dev, on remonte a la racine du dossier 'launcher'.
    """
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, rel)
    here = os.path.dirname(os.path.abspath(__file__))          # .../launcher/core
    root = os.path.normpath(os.path.join(here, ".."))           # .../launcher
    return os.path.normpath(os.path.join(root, rel))


def data_dir():
    """Dossier de donnees persistant du launcher (etat installe, config).

    Windows : %APPDATA%\\EbonholdLauncher ; fallback ~/.ebonhold-launcher ailleurs.
    """
    appdata = os.environ.get("APPDATA")
    base = os.path.join(appdata, "EbonholdLauncher") if appdata \
        else os.path.join(os.path.expanduser("~"), ".ebonhold-launcher")
    os.makedirs(base, exist_ok=True)
    return base
