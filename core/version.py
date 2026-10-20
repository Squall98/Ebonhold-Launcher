# -*- coding: utf-8 -*-
"""Version de l'application + comparaison de versions.

Une version est lue comme la suite de ses nombres : 'v.1.25' -> (1, 25),
'1.1.6-fr1' -> (1, 1, 6, 1), 'r139' -> (139,). Les zeros de fin ne comptent pas
('2.76' == '2.76.0'). Ainsi '1.1.7' et '1.2.0' sont bien plus recents que '1.1.6-fr1'
(l'ancienne lecture collait les chiffres : '1.1.6-fr1' devenait 1.1.61).
"""
import re

APP_VERSION = "2.0.1"


def _tuple(v):
    nums = [int(x) for x in re.findall(r"\d+", str(v or ""))]
    while nums and nums[-1] == 0:
        nums.pop()
    return tuple(nums)


def normalize(v):
    """Forme comparable d'une version (sert au test d'egalite)."""
    return ".".join(str(n) for n in _tuple(v)) or "0"


def is_newer(candidate, current):
    """True si `candidate` est strictement plus recent que `current`."""
    return _tuple(candidate) > _tuple(current)
