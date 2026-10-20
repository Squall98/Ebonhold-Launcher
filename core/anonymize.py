# -*- coding: utf-8 -*-
"""Anonymisation des textes et chemins joints a un signalement.

- C:\\Users\\<nom>\\...           -> C:\\Users\\***\\...   (tout lecteur, \\ ou /, doubles \\\\ du JSON)
- le nom d'utilisateur Windows, le nom du PC et le dossier du profil, partout ou ils apparaissent
- les adresses e-mail                -> <e-mail>
- des noms supplementaires fournis par l'appelant (ex. noms de compte du jeu) -> <compte>

Les noms de moins de 3 caracteres ne sont remplaces que dans les chemins (sinon on abimerait
tout le texte).
"""
import os
import re

MASK = "***"
ACCOUNT_MASK = "<compte>"

# Profils neutres : on ne les masque pas (ils n'identifient personne).
_NEUTRAL = {"public", "default", "default user", "all users", "defaultapppool", MASK}

# Segment de profil suivi d'un separateur : "Users\Jean Dupont\" (le nom peut contenir des espaces).
_PROFILE_MID = re.compile(r"(?i)((?:Users|Documents and Settings)(?:\\\\|\\|/)+)"
                          r"([^\\/\r\n\"'<>|:*?]+?)(?=\\|/)")
# Segment de profil en fin de chemin : "C:\Users\Jean" (sans espace, pour ne pas manger la ligne).
_PROFILE_END = re.compile(r"(?i)(\b[A-Za-z]:(?:\\\\|\\|/)+(?:Users|Documents and Settings)(?:\\\\|\\|/)+)"
                          r"([^\s\\/\"'<>|:*?]+)")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def _profile_sub(m):
    return m.group(1) + (m.group(2) if m.group(2).strip().lower() in _NEUTRAL else MASK)


def machine_names():
    """Noms propres a ce PC qui ne doivent jamais sortir : utilisateur, profil, nom du PC."""
    names = []
    for var in ("USERNAME", "COMPUTERNAME"):
        v = (os.environ.get(var) or "").strip()
        if v:
            names.append(v)
    prof = (os.environ.get("USERPROFILE") or "").strip().rstrip("\\/")
    if prof:
        names.append(os.path.basename(prof))
    dom = (os.environ.get("USERDOMAIN") or "").strip()
    if dom and dom.upper() not in ("WORKGROUP", "BUILTIN", "NT AUTHORITY"):
        names.append(dom)
    out = []
    for n in names:
        if n and n.lower() not in _NEUTRAL and n not in out:
            out.append(n)
    return out


def _replace_name(text, name, mask):
    if len(name) < 3:
        return text
    return re.sub(re.escape(name), mask, text, flags=re.IGNORECASE)


def text(s, accounts=()):
    """Version anonymisee d'un texte quelconque (journal, chemin, ligne de config)."""
    if s is None:
        return ""
    s = str(s)
    # 1) Dossier du profil tel quel (cas d'un profil hors de C:\Users, ex. D:\Profils\<nom>).
    prof = (os.environ.get("USERPROFILE") or "").strip().rstrip("\\/")
    if len(prof) > 3:
        masked = os.path.join(os.path.dirname(prof), MASK)
        for old, new in ((prof, masked), (prof.replace("\\", "/"), masked.replace("\\", "/")),
                         (prof.replace("\\", "\\\\"), masked.replace("\\", "\\\\"))):
            s = re.sub(re.escape(old), lambda _m, n=new: n, s, flags=re.IGNORECASE)
    # 2) Tout autre profil "Users\<nom>".
    s = _PROFILE_MID.sub(_profile_sub, s)
    s = _PROFILE_END.sub(_profile_sub, s)
    # 3) Noms de compte du jeu, puis noms propres au PC, partout.
    for a in sorted({a for a in accounts if a}, key=len, reverse=True):
        s = _replace_name(s, a, ACCOUNT_MASK)
    for n in sorted(machine_names(), key=len, reverse=True):
        s = _replace_name(s, n, MASK)
    # 4) Adresses e-mail.
    return _EMAIL.sub("<e-mail>", s)


def path(p):
    """Chemin anonymise pour affichage (C:\\Users\\***\\...)."""
    return text(p)
