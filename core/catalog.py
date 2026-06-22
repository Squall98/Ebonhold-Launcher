# -*- coding: utf-8 -*-
"""Catalogue : recuperation et lecture du manifest.json (liste des produits installables).

Source en ligne : repo dedie Squall98/Ebonhold-Launcher (branche main).
Fallback dev/offline : manifest.json embarque a la racine du launcher.
"""
import json
import os
import sys

from . import paths

MANIFEST_URL = (
    "https://raw.githubusercontent.com/Squall98/Ebonhold-Launcher/main/manifest.json"
)


def _load_local():
    # En dev (lance depuis les sources), privilegier manifest.dev.json (chemins locaux)
    # pour pouvoir tester l'installation hors-ligne. L'exe package, lui, lit manifest.json
    # (URLs GitHub de production).
    if not getattr(sys, "frozen", False):
        dev = paths.resource("manifest.dev.json")
        if os.path.isfile(dev):
            with open(dev, encoding="utf-8") as f:
                return json.load(f)
    with open(paths.resource("manifest.json"), encoding="utf-8") as f:
        return json.load(f)


def _load_remote(timeout=5):
    import urllib.request
    req = urllib.request.Request(MANIFEST_URL, headers={"User-Agent": "EbonholdLauncher"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch(prefer_remote=True):
    """Renvoie (manifest_dict, source) ou source vaut 'remote' ou 'local'.

    Essaie le manifeste en ligne ; en cas d'echec reseau, retombe sur la copie locale.
    """
    if prefer_remote:
        try:
            return _load_remote(), "remote"
        except Exception:
            pass
    return _load_local(), "local"


def products(manifest):
    return manifest.get("products", [])


def launcher_version(manifest):
    return manifest.get("launcher_version", "0.0.0")
