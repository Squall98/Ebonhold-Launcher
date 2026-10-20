# -*- coding: utf-8 -*-
"""Preferences de l'interface : %APPDATA%\\EbonholdLauncher\\prefs.json

Forme :
{
  "zoom": 1.0,              # zoom de toute la page, 0.8 a 1.6
  "first_run_done": false   # assistant du premier lancement termine
}
Ecriture atomique (fichier temporaire puis os.replace), sous verrou. Un fichier abime est garde
de cote (prefs.json.abime-<horodatage>) et on repart des valeurs par defaut, comme state.json.
"""
import json
import math
import os
import threading
import time

from . import paths

ZOOM_MIN = 0.8
ZOOM_MAX = 1.6
_DEFAULTS = {"zoom": 1.0, "first_run_done": False}
_LOCK = threading.RLock()


def _file():
    # Calcule a chaque appel : les tests redirigent APPDATA avant d'importer core,
    # et data_dir() recree le dossier s'il a disparu.
    return os.path.join(paths.data_dir(), "prefs.json")


def _clean_zoom(value):
    """Zoom valide (arrondi a 0.05 pres) ou ValueError."""
    if isinstance(value, bool):
        raise ValueError("zoom : nombre attendu")
    try:
        z = float(value)
    except (TypeError, ValueError):
        raise ValueError("zoom : nombre attendu")
    if math.isnan(z) or math.isinf(z):
        raise ValueError("zoom : nombre attendu")
    if z < ZOOM_MIN - 1e-6 or z > ZOOM_MAX + 1e-6:     # tolere 1.0 + 0.6 = 1.6000000000000001
        raise ValueError("zoom : entre %.1f et %.1f" % (ZOOM_MIN, ZOOM_MAX))
    return min(ZOOM_MAX, max(ZOOM_MIN, round(round(z / 0.05) * 0.05, 2)))


def _clean_bool(value):
    if isinstance(value, bool):
        return value
    raise ValueError("first_run_done : vrai ou faux attendu")


_VALIDATORS = {"zoom": _clean_zoom, "first_run_done": _clean_bool}


def _sanitize(data):
    """Ne garde que les cles connues et valides ; le reste reprend la valeur par defaut."""
    out = dict(_DEFAULTS)
    if isinstance(data, dict):
        for key, check in _VALIDATORS.items():
            if key in data:
                try:
                    out[key] = check(data[key])
                except ValueError:
                    pass
    return out


def _load():
    f = _file()
    try:
        with open(f, encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return dict(_DEFAULTS)
    except (ValueError, UnicodeDecodeError):
        # Fichier abime : garde de cote (jamais ecrase en silence), on repart des valeurs par defaut.
        try:
            os.replace(f, "%s.abime-%d" % (f, int(time.time())))
        except OSError:
            pass
        return dict(_DEFAULTS)
    except OSError:
        return dict(_DEFAULTS)
    return _sanitize(data)


def _save(data):
    f = _file()
    tmp = "%s.%d.%d.tmp" % (f, os.getpid(), threading.get_ident())
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, f)


def get():
    """Toutes les preferences : {"zoom": float, "first_run_done": bool}."""
    with _LOCK:
        return _load()


def set(key, value):     # noqa: A001 (nom impose par le contrat : prefs.set)
    """Change une preference. Renvoie {"ok": True, "prefs": {...}} ou {"ok": False, "error": "..."}."""
    check = _VALIDATORS.get(key)
    if check is None:
        return {"ok": False, "error": "Reglage inconnu : %s" % str(key)[:40]}
    try:
        clean = check(value)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    with _LOCK:
        data = _load()
        data[key] = clean
        try:
            _save(data)
        except OSError as e:
            return {"ok": False, "error": "Impossible d'enregistrer le reglage (%s)." % e.strerror}
        return {"ok": True, "prefs": dict(data)}
