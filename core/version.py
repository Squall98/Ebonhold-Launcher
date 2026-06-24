# -*- coding: utf-8 -*-
"""Version de l'application + comparaison de versions (semver simplifie)."""

APP_VERSION = "1.0.3"


def _tuple(v):
    parts = []
    for p in str(v).strip().lstrip("v").split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def is_newer(candidate, current):
    """True si `candidate` est strictement plus recent que `current`."""
    return _tuple(candidate) > _tuple(current)
