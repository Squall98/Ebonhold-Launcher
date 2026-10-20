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


_CACHE_FILE = os.path.join(paths.data_dir(), "manifest-cache.json")


def _valid(man):
    return isinstance(man, dict) and isinstance(man.get("products"), list)


def _test_catalogue():
    """Session de test avant publication : EBONHOLD_CATALOGUE=<manifeste local> remplace le
    catalogue en ligne (addons pas encore publies, installes depuis des zips locaux)."""
    p = os.environ.get("EBONHOLD_CATALOGUE", "")
    if p and os.path.isfile(p):
        with open(p, encoding="utf-8") as f:
            man = json.load(f)
        if _valid(man):
            return man
    return None


def _load_remote(timeout=5):
    test = _test_catalogue()
    if test is not None:
        return test
    import urllib.request
    req = urllib.request.Request(MANIFEST_URL, headers={"User-Agent": "EbonholdLauncher"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        man = json.loads(r.read().decode("utf-8"))
    if not _valid(man):
        raise ValueError("catalogue en ligne illisible")
    _save_cache(man)
    return man


def _save_cache(man):
    """Garde le dernier catalogue en ligne : il sert au prochain demarrage et hors ligne."""
    tmp = _CACHE_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(man, f, ensure_ascii=False)
        os.replace(tmp, _CACHE_FILE)
    except OSError:
        pass


def _load_cache():
    try:
        with open(_CACHE_FILE, encoding="utf-8") as f:
            man = json.load(f)
        return man if _valid(man) else None
    except (OSError, ValueError):
        return None


def fetch_offline():
    """Catalogue sans reseau : le dernier catalogue en ligne garde sur le disque, sauf s'il
    date d'avant cette version du launcher (le catalogue embarque est alors plus recent)."""
    from . import version
    test = _test_catalogue()
    if test is not None:
        return test, "local"
    local = _load_local()
    cache = _load_cache()
    if cache and not version.is_newer(launcher_version(local), launcher_version(cache)):
        return cache, "cache"
    return local, "local"


def fetch(prefer_remote=True):
    """Renvoie (manifest_dict, source) ou source vaut 'remote', 'cache' ou 'local'.

    Essaie le manifeste en ligne ; en cas d'echec reseau, retombe sur la copie hors ligne.
    """
    if prefer_remote:
        try:
            return _load_remote(), "remote"
        except Exception:
            pass
    return fetch_offline()


def products(manifest):
    return manifest.get("products", [])


def launcher_version(manifest):
    return manifest.get("launcher_version", "0.0.0")
