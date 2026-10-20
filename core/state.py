# -*- coding: utf-8 -*-
"""Etat local persistant : dossier WoW choisi + modules installes et leur version.

Fichier : %APPDATA%\\EbonholdLauncher\\state.json
Forme :
{
  "wow_path": "D:\\ebonhold\\Ebonhold",
  "installed": {
     "ebonholdfr":  {"version": "3.1", "files": ["Interface/AddOns/EbonholdFR"]},
     "patch-z":     {"version": "2026.06", "files": ["Data/patch-Z.MPQ"]}
  }
}
Les chemins de 'files' sont RELATIFS a wow_path pour pouvoir desinstaller proprement.
"""
import json
import os
import threading
import time

from . import paths

_STATE_FILE = os.path.join(paths.data_dir(), "state.json")
_DEFAULT = {"wow_path": "", "installed": {}}
# Plusieurs threads (installations, detection du jeu) lisent et ecrivent l'etat :
# chaque lecture-modification-ecriture se fait sous ce verrou.
_LOCK = threading.RLock()


def _default():
    return {"wow_path": "", "installed": {}}


def load():
    with _LOCK:
        try:
            with open(_STATE_FILE, encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            return _default()
        except ValueError:
            # Fichier abime : on le garde de cote (jamais ecrase en silence) et on repart a vide.
            try:
                os.replace(_STATE_FILE, "%s.abime-%d" % (_STATE_FILE, int(time.time())))
            except OSError:
                pass
            return _default()
        if not isinstance(data, dict):
            return _default()
        data.setdefault("wow_path", "")
        data.setdefault("installed", {})
        return data


def save(data):
    with _LOCK:
        tmp = "%s.%d.%d.tmp" % (_STATE_FILE, os.getpid(), threading.get_ident())
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, _STATE_FILE)


def get_wow_path():
    return load().get("wow_path", "")


def set_wow_path(path):
    with _LOCK:
        data = load()
        data["wow_path"] = path
        save(data)


def get_installed(product_id):
    """Renvoie l'entree installee {version, files} ou None."""
    return load().get("installed", {}).get(product_id)


def mark_installed(product_id, version, files):
    with _LOCK:
        data = load()
        data["installed"][product_id] = {"version": version, "files": files}
        save(data)


def mark_removed(product_id):
    with _LOCK:
        data = load()
        data["installed"].pop(product_id, None)
        save(data)
