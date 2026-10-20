# -*- coding: utf-8 -*-
"""Infos DU JEU jointes a un signalement de bug.

Uniquement ce qui touche au jeu : versions de Wow.exe et des DLL Ebonhold, patchs MPQ (taille,
date, sha256 des petits patchs), dossiers de langue, quelques reglages de WTF\\Config.wtf, addons
et leurs versions, fin des journaux du jeu.
JAMAIS d'infos Windows (version, materiel, nom du PC, programmes installes) ni rien qui
identifie un compte (accountName, accountList, lastCharacterIndex, dossiers WTF\\Account\\<compte>).
Tous les chemins et textes passent par anonymize.text().

    info = collect(wow_path)      # dict
    texte = to_text(info)         # apercu lisible montre au joueur, joint au signalement
"""
import base64
import glob
import hashlib
import os
import re
import struct
import threading
import time

from . import anonymize

DLL_NAMES = ("ebonhold.dll", "ClientExt.dll", "AwesomeWotlkLib.dll")
SHA_MAX_SIZE = 100 * 1024 * 1024            # sha256 seulement pour les patchs < 100 Mo
EBONHOLD_LOG_LINES = 80
GAME_LOG_LINES = 60
GAME_LOGS = ("FrameXML.log", "GlueXML.log")
ERROR_LINES = 60
MAX_ADDONS = 300

# Reglages de Config.wtf montres (liste blanche, comparaison en minuscules).
CONFIG_KEYS = ("locale", "realmList", "realmName", "patchlist", "gxApi", "gxWindow", "gxMaximize",
               "gxResolution", "gxRefresh", "gxVSync", "gxMultisample", "gxTripleBuffer",
               "uiScale", "useUiScale", "movie", "hwDetect")
# Defense en profondeur : meme si la liste blanche change, ces cles ne sortent jamais.
_FORBIDDEN_KEY = re.compile(r"(?i)^(account|lastchar|lastcharacter|password|pass|token|savedaccount"
                            r"|realmid|servername|login)")
_SET_RE = re.compile(r'(?im)^\s*SET\s+(\S+)\s+"?(.*?)"?\s*$')
_TOC_RE = re.compile(r"^\s*##\s*([A-Za-z\-]+)\s*:\s*(.*?)\s*$")
_COLOR_RE = re.compile(r"\|c[0-9a-fA-F]{8}|\|r")
_LOCALE_RE = re.compile(r"^[a-z]{2}[A-Z]{2}$")
_REALM_RE = re.compile(r'(?im)^\s*set\s+realmlist\s+"?([^"\r\n]+?)"?\s*$')
# Lignes des rapports d'erreur (Errors\*.txt) qui decrivent la machine ou la personne : retirees.
_ERROR_DROP = re.compile(r"(?i)^\s*(user|computer|utilisateur|ordinateur|machine|os|operating system"
                         r"|system|systeme|processor|processeur|cpu|memory|memoire|ram|physical"
                         r"|video|display|graphics|gpu|carte|windows|domain|ip)\b[^:]*:")

_SHA_CACHE = {}
_SHA_LOCK = threading.Lock()


# ---------------------------------------------------------------- petits outils


def _stat(path):
    try:
        st = os.stat(path)
    except OSError:
        return None
    return {"size": st.st_size, "mtime": st.st_mtime}


def fmt_size(n):
    """Taille lisible a la francaise : 950 o, 12 Ko, 21,3 Mo, 2,4 Go."""
    if n is None:
        return "?"
    for unit, div in (("Go", 1024 ** 3), ("Mo", 1024 ** 2), ("Ko", 1024)):
        if n >= div:
            v = n / div
            s = ("%.1f" % v) if v < 100 else ("%d" % round(v))
            return "%s %s" % (s.replace(".", ","), unit)
    return "%d o" % n


def fmt_date(ts):
    return time.strftime("%d/%m/%Y %H:%M", time.localtime(ts)) if ts else "?"


def digests(path, size=None, mtime=None):
    """(sha256 hex, md5 base64) d'un fichier, gardes en memoire tant que taille et date ne changent
    pas. Le md5 base64 est la forme que compare le launcher officiel (verification_cache.json,
    ebonhold.log : "patch-5.MPQ local=... expected=...")."""
    key = (os.path.normcase(path), size, mtime)
    with _SHA_LOCK:
        if key in _SHA_CACHE:
            return _SHA_CACHE[key]
    h, m = hashlib.sha256(), hashlib.md5()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
                m.update(chunk)
    except OSError:
        return "", ""
    res = (h.hexdigest(), base64.b64encode(m.digest()).decode("ascii"))
    with _SHA_LOCK:
        _SHA_CACHE[key] = res
    return res


def file_version(path):
    """Version 'a.b.c.d' de la ressource de version d'un .exe/.dll (Windows), ou ''."""
    if os.name != "nt" or not os.path.isfile(path):
        return ""
    try:
        import ctypes
        from ctypes import wintypes
        ver = ctypes.WinDLL("version")
        ver.GetFileVersionInfoSizeW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
        ver.GetFileVersionInfoSizeW.restype = wintypes.DWORD
        ver.GetFileVersionInfoW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                            ctypes.c_void_p]
        ver.GetFileVersionInfoW.restype = wintypes.BOOL
        ver.VerQueryValueW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR,
                                       ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.UINT)]
        ver.VerQueryValueW.restype = wintypes.BOOL
        dummy = wintypes.DWORD(0)
        size = ver.GetFileVersionInfoSizeW(path, ctypes.byref(dummy))
        if not size:
            return ""
        buf = ctypes.create_string_buffer(size)
        if not ver.GetFileVersionInfoW(path, 0, size, buf):
            return ""
        ptr, n = ctypes.c_void_p(), wintypes.UINT(0)
        if not ver.VerQueryValueW(buf, "\\", ctypes.byref(ptr), ctypes.byref(n)) or n.value < 16:
            return ""
        sig, _sv, ms, ls = struct.unpack("<IIII", ctypes.string_at(ptr.value, 16))
        if sig != 0xFEEF04BD:
            return ""
        return "%d.%d.%d.%d" % (ms >> 16, ms & 0xFFFF, ls >> 16, ls & 0xFFFF)
    except Exception:        # noqa: BLE001
        return ""


def _decode(raw):
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252", "replace")


def tail_lines(path, n, max_bytes=512 * 1024):
    """n dernieres lignes d'un fichier texte (lit au plus max_bytes depuis la fin)."""
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - max_bytes))
            raw = f.read()
    except OSError:
        return []
    lines = _decode(raw).splitlines()
    if size > max_bytes and lines:
        lines = lines[1:]              # premiere ligne probablement coupee
    return [l.rstrip() for l in lines[-n:]]


def head_lines(path, n, max_bytes=256 * 1024):
    try:
        with open(path, "rb") as f:
            raw = f.read(max_bytes)
    except OSError:
        return []
    return [l.rstrip() for l in _decode(raw).splitlines()[:n]]


def _children(path):
    try:
        return sorted(os.listdir(path), key=str.lower)
    except OSError:
        return []


def _find_child(path, name):
    """Nom reel d'un enfant (insensible a la casse) ou None."""
    low = name.lower()
    for n in _children(path):
        if n.lower() == low:
            return os.path.join(path, n)
    return None


# ---------------------------------------------------------------- collecte


def _file_entry(path, name, with_version=False):
    st = _stat(path) if path else None
    e = {"name": name, "present": bool(st)}
    if st:
        e.update(size=st["size"], mtime=st["mtime"])
        if with_version:
            e["version"] = file_version(path)
    return e


def _mpq_list(folder):
    out = []
    for n in _children(folder):
        if not n.lower().endswith(".mpq"):
            continue
        p = os.path.join(folder, n)
        st = _stat(p)
        if not st or not os.path.isfile(p):
            continue
        e = {"name": n, "size": st["size"], "mtime": st["mtime"]}
        if n.lower().startswith("patch") and st["size"] < SHA_MAX_SIZE:
            e["sha256"], e["md5"] = digests(p, st["size"], st["mtime"])
        out.append(e)
    return out


def _parse_config(path):
    """(reglages montres, noms de compte a masquer) depuis WTF\\Config.wtf."""
    shown, accounts = {}, []
    try:
        with open(path, "rb") as f:
            txt = _decode(f.read(256 * 1024))
    except OSError:
        return None, accounts
    allowed = {k.lower(): k for k in CONFIG_KEYS}
    for key, value in _SET_RE.findall(txt):
        low = key.lower()
        if low in ("accountname", "accountlist"):
            accounts += [a for a in re.split(r"[|;,]", value) if a.strip()]
            continue
        if _FORBIDDEN_KEY.match(key) or low not in allowed:
            continue
        shown[allowed[low]] = value
    return shown, accounts


def _account_dirs(game_dir):
    acc = _find_child(game_dir, "WTF")
    acc = _find_child(acc, "Account") if acc else None
    if not acc:
        return []
    return [n for n in _children(acc) if n.lower() != "savedvariables" and os.path.isdir(os.path.join(acc, n))]


def _addons(game_dir):
    inter = _find_child(game_dir, "Interface")
    root = _find_child(inter, "AddOns") if inter else None
    out, blizzard = [], 0
    if not root:
        return out, blizzard
    for n in _children(root):
        d = os.path.join(root, n)
        if not os.path.isdir(d):
            continue
        if n.lower().startswith("blizzard_"):
            blizzard += 1
            continue
        if len(out) >= MAX_ADDONS:
            break
        toc = _find_child(d, n + ".toc")
        if not toc:
            tocs = [c for c in _children(d) if c.lower().endswith(".toc")]
            toc = os.path.join(d, tocs[0]) if tocs else None
        e = {"name": n, "version": "", "interface": "", "title": "", "toc": bool(toc)}
        if toc:
            for line in head_lines(toc, 60, 8192):
                m = _TOC_RE.match(line)
                if not m:
                    continue
                k = m.group(1).lower()
                if k == "version":
                    e["version"] = m.group(2)[:40]
                elif k == "interface":
                    e["interface"] = m.group(2)[:20]
                elif k == "title":
                    e["title"] = _COLOR_RE.sub("", m.group(2))[:80]
        out.append(e)
    return out, blizzard


def _logs(game_dir, accounts):
    logs = []
    eb = _find_child(game_dir, "ebonhold.log")
    if eb:
        st = _stat(eb)
        logs.append({"name": "ebonhold.log", "mtime": st["mtime"] if st else 0,
                     "what": "%d dernieres lignes" % EBONHOLD_LOG_LINES,
                     "lines": [anonymize.text(l, accounts) for l in tail_lines(eb, EBONHOLD_LOG_LINES)]})
    ldir = _find_child(game_dir, "Logs")
    for name in GAME_LOGS:
        p = _find_child(ldir, name) if ldir else None
        if not p:
            continue
        st = _stat(p)
        logs.append({"name": "Logs\\" + name, "mtime": st["mtime"] if st else 0,
                     "what": "%d dernieres lignes" % GAME_LOG_LINES,
                     "lines": [anonymize.text(l, accounts) for l in tail_lines(p, GAME_LOG_LINES)]})
    edir = _find_child(game_dir, "Errors")
    if edir:
        files = [p for p in glob.glob(os.path.join(edir, "*.txt")) if os.path.isfile(p)]
        if files:
            last = max(files, key=lambda p: os.path.getmtime(p))
            kept = [l for l in head_lines(last, 400) if not _ERROR_DROP.match(l)][:ERROR_LINES]
            logs.append({"name": "Errors\\" + os.path.basename(last), "mtime": os.path.getmtime(last),
                         "what": "debut du dernier rapport d'erreur (%d lignes)" % ERROR_LINES,
                         "lines": [anonymize.text(l, accounts) for l in kept]})
    return logs


def collect(wow_path, include_logs=True):
    """Toutes les infos du jeu utiles a un signalement (dict serialisable en JSON)."""
    info = {"path": anonymize.path(wow_path or ""), "found": False}
    if not wow_path or not os.path.isdir(wow_path):
        return info
    info["found"] = True
    accounts = _account_dirs(wow_path)
    names = {n.lower(): n for n in _children(wow_path)}

    exe = names.get("wow.exe")
    exe_path = os.path.join(wow_path, exe) if exe else None
    info["wow_exe"] = _file_entry(exe_path, exe or "Wow.exe", with_version=True)
    info["dlls"] = [_file_entry(os.path.join(wow_path, names[d.lower()]) if d.lower() in names else None,
                                d, with_version=True) for d in DLL_NAMES]
    info["ebonhold_exe"] = _file_entry(os.path.join(wow_path, names["ebonhold.exe"])
                                       if "ebonhold.exe" in names else None, "ebonhold.exe",
                                       with_version=True)

    data = _find_child(wow_path, "Data")
    info["mpq"] = _mpq_list(data) if data else []
    info["locales"] = []
    if data:
        for n in _children(data):
            d = os.path.join(data, n)
            if _LOCALE_RE.match(n) and os.path.isdir(d):
                rl = _find_child(d, "realmlist.wtf")
                realm = ""
                if rl:
                    m = _REALM_RE.findall("\n".join(head_lines(rl, 20, 4096)))
                    realm = m[0] if m else ""
                info["locales"].append({"name": n, "mpq": _mpq_list(d), "realmlist": realm})

    wtf = _find_child(wow_path, "WTF")
    cfg = _find_child(wtf, "Config.wtf") if wtf else None
    shown, cfg_accounts = _parse_config(cfg) if cfg else (None, [])
    accounts += cfg_accounts
    info["config"] = shown            # None = Config.wtf absent
    info["addons"], info["blizzard_addons"] = _addons(wow_path)
    info["logs"] = _logs(wow_path, accounts) if include_logs else []
    # Derniere passe : rien de ce qui sort ne doit contenir un nom de compte ou de PC.
    return _scrub(info, accounts)


def _scrub(obj, accounts):
    if isinstance(obj, str):
        return anonymize.text(obj, accounts)
    if isinstance(obj, list):
        return [_scrub(x, accounts) for x in obj]
    if isinstance(obj, dict):
        return {k: _scrub(v, accounts) for k, v in obj.items()}
    return obj


# ---------------------------------------------------------------- texte lisible


def _entry_line(e):
    if not e.get("present"):
        return "%s : absent" % e["name"]
    parts = [fmt_size(e.get("size")), fmt_date(e.get("mtime"))]
    if e.get("version"):
        parts.insert(0, "version %s" % e["version"])
    return "%s : %s" % (e["name"], ", ".join(parts))


def _mpq_line(e):
    s = "  %-28s %9s  %s" % (e["name"], fmt_size(e["size"]), fmt_date(e["mtime"]))
    if e.get("sha256"):
        s += "  md5 %s  sha256 %s" % (e.get("md5", ""), e["sha256"])
    return s


def to_text(info):
    """Texte lisible des infos du jeu (apercu montre au joueur avant l'envoi)."""
    out = ["== Jeu =="]
    out.append("Dossier : %s" % (info.get("path") or "(non choisi)"))
    if not info.get("found"):
        out.append("Dossier du jeu introuvable : aucune info du jeu jointe.")
        return "\n".join(out)
    out.append(_entry_line(info["wow_exe"]))
    for d in info.get("dlls", []):
        out.append(_entry_line(d))
    if info.get("ebonhold_exe", {}).get("present"):
        out.append(_entry_line(info["ebonhold_exe"]))
    cfg = info.get("config")
    if cfg is None:
        out.append("WTF\\Config.wtf : absent")
    else:
        out.append("WTF\\Config.wtf : " + (" ; ".join("%s=%s" % kv for kv in cfg.items()) or "(vide)"))

    out.append("")
    out.append("== Patchs (Data) ==")
    if info.get("mpq"):
        out += [_mpq_line(e) for e in info["mpq"]]
    else:
        out.append("  aucun MPQ (dossier Data absent ?)")
    for loc in info.get("locales", []):
        out.append("")
        out.append("== Langue Data\\%s ==%s" % (loc["name"],
                   ("  (realmlist %s)" % loc["realmlist"]) if loc.get("realmlist") else ""))
        out += [_mpq_line(e) for e in loc["mpq"]] or ["  aucun MPQ"]
    if not any(l["name"] == "frFR" for l in info.get("locales", [])):
        out.append("")
        out.append("Data\\frFR : absent (pas de pack de langue francais)")

    out.append("")
    addons = info.get("addons", [])
    out.append("== Addons (Interface\\AddOns) : %d%s ==" % (
        len(addons), (" + %d dossiers Blizzard_*" % info["blizzard_addons"]) if info.get("blizzard_addons") else ""))
    for a in addons:
        bits = [a["name"]]
        bits.append(a["version"] or "(version ?)")
        if a.get("interface"):
            bits.append("interface %s" % a["interface"])
        if not a.get("toc"):
            bits.append("SANS .toc")
        out.append("  " + " | ".join(bits))

    for lg in info.get("logs", []):
        out.append("")
        out.append("--- %s (%s, modifie le %s) ---" % (lg["name"], lg["what"], fmt_date(lg.get("mtime"))))
        out += lg["lines"] or ["(vide)"]
    return "\n".join(out)
