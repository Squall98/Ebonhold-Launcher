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

from . import paths

_STATE_FILE = os.path.join(paths.data_dir(), "state.json")
_DEFAULT = {"wow_path": "", "installed": {}}


def load():
    try:
        with open(_STATE_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, ValueError):
        return dict(_DEFAULT)
    data.setdefault("wow_path", "")
    data.setdefault("installed", {})
    return data


def save(data):
    tmp = _STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _STATE_FILE)


def get_wow_path():
    return load().get("wow_path", "")


def set_wow_path(path):
    data = load()
    data["wow_path"] = path
    save(data)


def get_installed(product_id):
    """Renvoie l'entree installee {version, files} ou None."""
    return load().get("installed", {}).get(product_id)


def mark_installed(product_id, version, files):
    data = load()
    data["installed"][product_id] = {"version": version, "files": files}
    save(data)


def mark_removed(product_id):
    data = load()
    data["installed"].pop(product_id, None)
    save(data)
