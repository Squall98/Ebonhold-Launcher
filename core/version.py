# -*- coding: utf-8 -*-
"""Version de l'application + comparaison de versions (semver simplifie)."""
import re

APP_VERSION = "1.0.8"


def normalize(v):
    """Reduit une version a sa forme numerique pointee : 'v.1.25' -> '1.25', 'r139' -> '139'."""
    s = re.sub(r"[^\d.]", "", str(v))
    s = re.sub(r"\.+", ".", s).strip(".")
    return s or "0"


def _tuple(v):
    return tuple(int(x) for x in normalize(v).split("."))


def is_newer(candidate, current):
    """True si `candidate` est strictement plus recent que `current`."""
    return _tuple(candidate) > _tuple(current)
