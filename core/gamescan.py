# -*- coding: utf-8 -*-
"""Recherche des installations du jeu (WoW 3.3.5a) sur le PC du joueur.

- quick_detect() : instantane, sans parcours de disque. Emplacements connus (dossier du launcher
  officiel, Program Files, X:\\Games...), premier niveau des racines de disques, cles de
  desinstallation du registre (LECTURE seule) et raccourcis du Bureau / menu Demarrer.
- scan(progress) : parcours des disques FIXES (ni reseau ni amovibles) a la recherche de Wow.exe,
  profondeur limitee, dossiers systeme sautes, arret au bout du temps imparti. A ne lancer
  qu'apres accord du joueur.

Chaque dossier trouve devient un Candidat :
  {"path": chemin reel, "is_ebonhold": bool, "label": texte lisible (chemin anonymise),
   "has_exe": bool (Wow.exe present), "reason": pourquoi on pense que c'est (ou non) Ebonhold}
is_ebonhold faux = autre serveur prive : l'interface le montre grise, mais il reste selectionnable.
"""
import collections
import os
import re
import struct
import time

from . import anonymize

EXE_NAMES = ("wow.exe",)
_EBONHOLD_FILES = ("ebonhold.dll", "ebonhold.exe")
_EBONHOLD_REALM = "project-ebonhold"
_DATA_MARKERS = ("patch-5.mpq", "common.mpq", "lichking.mpq", "patch.mpq", "common-2.mpq")
_LOCALE_RE = re.compile(r"^[a-z]{2}[A-Z]{2}$")
_REALM_RE = re.compile(r'(?im)^\s*set\s+realmlist\s+"?([^"\r\n]+?)"?\s*$')

# Noms de dossiers jamais parcourus pendant le scan (comparaison en minuscules).
SKIP_NAMES = {
    "windows", "$recycle.bin", "system volume information", "$windows.~bt", "$windows.~ws",
    "$winreagent", "$sysreset", "$getcurrent", "recovery", "perflogs", "config.msi", "msocache",
    "windowsapps", "winsxs", "node_modules", ".git", ".svn", ".hg", "__pycache__", ".venv",
    "venv", "site-packages", "shadercache", "temp", "$av_asw", "intel", "amd", "nvidia",
    "drivers", "driverstore", "packages", "cache", "caches", "crashdumps", ".cache", ".npm",
    ".nuget", ".gradle", ".m2", ".cargo", ".rustup", "docker", "wsl",
}
# Fins de chemin jamais parcourues (separateurs normalises en \\, minuscules).
SKIP_SUFFIXES = (
    "\\programdata\\microsoft", "\\programdata\\package cache", "\\appdata\\local\\temp",
    "\\appdata\\local\\microsoft", "\\appdata\\roaming\\microsoft", "\\appdata\\local\\packages",
    "\\appdata\\local\\google", "\\appdata\\local\\mozilla", "\\appdata\\roaming\\mozilla",
    "\\appdata\\local\\nvidia", "\\steamapps\\shadercache", "\\steamapps\\downloading",
    "\\steamapps\\workshop", "\\program files\\windowsapps", "\\program files\\common files",
    "\\program files (x86)\\common files", "\\program files (x86)\\microsoft",
    "\\program files\\microsoft office", "\\microsoft visual studio", "\\windows kits",
)

_DRIVE_FIXED = 3


# ---------------------------------------------------------------- outils communs


def _key(path):
    return os.path.normcase(os.path.abspath(path)).rstrip("\\/")


def fixed_drives():
    """Racines des disques fixes ("C:\\", "D:\\"...). Hors Windows : ["/"]."""
    if os.name != "nt":
        return ["/"]
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        mask = k32.GetLogicalDrives()
        out = []
        for i in range(26):
            if mask & (1 << i):
                root = "%s:\\" % chr(65 + i)
                if k32.GetDriveTypeW(ctypes.c_wchar_p(root)) == _DRIVE_FIXED:
                    out.append(root)
        return out
    except Exception:        # noqa: BLE001
        return [r for r in ("C:\\", "D:\\", "E:\\", "F:\\") if os.path.isdir(r)]


def _listdir_lower(path):
    try:
        return {n.lower(): n for n in os.listdir(path)}
    except OSError:
        return {}


def _read_small(path, limit=65536):
    try:
        with open(path, "rb") as f:
            return f.read(limit).decode("utf-8", "replace")
    except OSError:
        return ""


def realmlists(game_dir, names=None):
    """Realmlists declares par l'install : Data\\<langue>\\realmlist.wtf puis WTF\\Config.wtf."""
    found = []
    names = names if names is not None else _listdir_lower(game_dir)
    data = names.get("data")
    if data:
        data_dir = os.path.join(game_dir, data)
        for sub in sorted(_listdir_lower(data_dir).values()):
            if _LOCALE_RE.match(sub):
                rl = os.path.join(data_dir, sub, "realmlist.wtf")
                if os.path.isfile(rl):
                    found += _REALM_RE.findall(_read_small(rl, 4096))
    wtf = names.get("wtf")
    if wtf:
        found += _REALM_RE.findall(_read_small(os.path.join(game_dir, wtf, "Config.wtf")))
    out = []
    for r in found:
        r = r.strip()
        if r and r.lower() not in [o.lower() for o in out]:
            out.append(r)
    return out


def examine(game_dir):
    """Candidat pour ce dossier, ou None s'il ne ressemble pas a une install du jeu."""
    if not game_dir or not os.path.isdir(game_dir):
        return None
    names = _listdir_lower(game_dir)
    has_exe = any(n in names for n in EXE_NAMES)
    data_names = _listdir_lower(os.path.join(game_dir, names["data"])) if "data" in names else {}
    has_data = any(m in data_names for m in _DATA_MARKERS)
    if not has_exe and not has_data:
        return None
    realms = realmlists(game_dir, names)
    reason = ""
    for f in _EBONHOLD_FILES:
        if f in names:
            reason = "%s present" % names[f]
            break
    if not reason:
        for r in realms:
            if _EBONHOLD_REALM in r.lower():
                reason = "realmlist %s" % r
                break
    if not reason and "patch-5.mpq" in data_names and "verification_cache.json" in names:
        reason = "patch-5.MPQ + verification_cache.json (launcher officiel)"
    is_eb = bool(reason)
    shown = anonymize.path(os.path.abspath(game_dir))
    if is_eb:
        label = "Ebonhold — %s" % shown
    else:
        realm = realms[0] if realms else "inconnu"
        label = "Autre serveur (realmlist %s) — %s" % (realm, shown)
        reason = "realmlist %s" % realm if realms else "aucun signe d'Ebonhold"
    if not has_exe:
        label += " (Wow.exe absent)"
    return {"path": os.path.abspath(game_dir), "is_ebonhold": is_eb, "label": label,
            "has_exe": has_exe, "reason": reason}


class _Results:
    """Candidats sans doublon (chemins insensibles a la casse)."""

    def __init__(self):
        self.items = []
        self._seen = set()

    def add_dir(self, d):
        if not d:
            return None
        k = _key(d)
        if k in self._seen:
            return None
        self._seen.add(k)
        c = examine(d)
        if c:
            self.items.append(c)
        return c

    def add_candidate(self, c):
        k = _key(c["path"])
        if k not in self._seen:
            self._seen.add(k)
            self.items.append(c)

    def sorted(self):
        # Ebonhold d'abord, puis ceux qui ont Wow.exe ; ordre de decouverte sinon.
        return sorted(self.items, key=lambda c: (not c["is_ebonhold"], not c["has_exe"]))


# ---------------------------------------------------------------- detection rapide


def _known_dirs(drives):
    env = os.environ.get
    out = []
    for var in ("LOCALAPPDATA", "APPDATA", "ProgramData", "USERPROFILE"):
        base = env(var)
        if not base:
            continue
        for sub in ("ebonhold", os.path.join("ebonhold", "Ebonhold"), "Ebonhold",
                    os.path.join("Programs", "ebonhold"), os.path.join("Games", "Ebonhold")):
            out.append(os.path.join(base, sub))
    for var in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432"):
        base = env(var)
        if base:
            out += [os.path.join(base, "Ebonhold"), os.path.join(base, "ebonhold", "Ebonhold")]
    for root in drives:
        for sub in ("ebonhold", os.path.join("ebonhold", "Ebonhold"), os.path.join("Games", "Ebonhold"),
                    os.path.join("Jeux", "Ebonhold"), "Program Files\\Ebonhold",
                    "Program Files (x86)\\Ebonhold"):
            out.append(os.path.join(root, sub))
    return out


def _shallow_dirs(drives):
    """Premier niveau des racines de disques et des dossiers de jeux habituels."""
    parents = list(drives)
    for root in drives:
        for sub in ("Games", "Jeux", "Program Files", "Program Files (x86)"):
            parents.append(os.path.join(root, sub))
    out = []
    for p in parents:
        for n in _listdir_lower(p).values():
            full = os.path.join(p, n)
            if n.lower() not in SKIP_NAMES and not n.startswith("$") and os.path.isdir(full):
                out.append(full)
    return out


def _registry_dirs():
    """Dossiers declares par les cles de desinstallation qui evoquent Ebonhold (lecture seule)."""
    try:
        import winreg
    except ImportError:
        return []
    out = []
    roots = ((winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
             (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
             (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"))
    for hive, sub in roots:
        try:
            key = winreg.OpenKey(hive, sub, 0, winreg.KEY_READ)
        except OSError:
            continue
        with key:
            i = 0
            while i < 5000:
                try:
                    name = winreg.EnumKey(key, i)
                except OSError:
                    break
                i += 1
                try:
                    with winreg.OpenKey(key, name, 0, winreg.KEY_READ) as k:
                        vals = {}
                        for v in ("DisplayName", "InstallLocation", "UninstallString", "DisplayIcon"):
                            try:
                                vals[v] = str(winreg.QueryValueEx(k, v)[0] or "")
                            except OSError:
                                vals[v] = ""
                except OSError:
                    continue
                blob = (name + " " + vals["DisplayName"] + " " + vals["InstallLocation"]).lower()
                if "ebonhold" not in blob:
                    continue
                if vals["InstallLocation"]:
                    out.append(vals["InstallLocation"].strip().strip('"'))
                for v in ("UninstallString", "DisplayIcon"):
                    exe = _exe_from_command(vals[v])
                    if exe:
                        out.append(os.path.dirname(exe))
    return out


def _exe_from_command(cmd):
    """'"C:\\x\\uninstall.exe" /S' ou 'C:\\x\\app.exe,0' -> 'C:\\x\\uninstall.exe'."""
    cmd = (cmd or "").strip()
    if not cmd:
        return ""
    if cmd.startswith('"'):
        end = cmd.find('"', 1)
        return cmd[1:end] if end > 1 else ""
    m = re.match(r"(?i)(.+?\.exe)\b", cmd)
    return m.group(1) if m else ""


def lnk_target(path):
    """Cible d'un raccourci .lnk (format MS-SHLLINK, LinkInfo / LocalBasePath), ou ''."""
    try:
        with open(path, "rb") as f:
            raw = f.read(65536)
    except OSError:
        return ""
    target = _lnk_local_base_path(raw)
    if target:
        return target
    # Repli : chemin "X:\\...\\ebonhold.exe|wow.exe" ecrit en UTF-16 quelque part dans le fichier.
    for start in (0, 1):
        m = re.search(r"(?i)[A-Z]:\\[^\x00<>|\"*?]{0,240}?\\(?:ebonhold|wow)\.exe",
                      raw[start:].decode("utf-16-le", "ignore"))
        if m:
            return m.group(0)
    return ""


def _lnk_local_base_path(raw):
    try:
        if len(raw) < 0x4C or struct.unpack_from("<I", raw, 0)[0] != 0x4C:
            return ""
        flags = struct.unpack_from("<I", raw, 0x14)[0]
        pos = 0x4C
        if flags & 0x01:                                    # HasLinkTargetIDList
            pos += 2 + struct.unpack_from("<H", raw, pos)[0]
        if not flags & 0x02:                                # pas de LinkInfo
            return ""
        li = pos
        hsize = struct.unpack_from("<I", raw, li + 4)[0]
        lflags = struct.unpack_from("<I", raw, li + 8)[0]
        if not lflags & 0x01:                               # pas de VolumeIDAndLocalBasePath
            return ""
        if hsize >= 0x24:
            off_u = struct.unpack_from("<I", raw, li + 0x1C)[0]
            if off_u:
                start = li + off_u
                end = start
                while end + 1 < len(raw) and raw[end:end + 2] != b"\x00\x00":
                    end += 2
                return raw[start:end].decode("utf-16-le", "replace")
        off = struct.unpack_from("<I", raw, li + 0x10)[0]
        end = raw.find(b"\x00", li + off)
        if end == -1:
            return ""
        return raw[li + off:end].decode("mbcs" if os.name == "nt" else "latin-1", "replace")
    except (struct.error, LookupError):
        return ""


def _shortcut_dirs():
    env = os.environ.get
    bases = []
    prof = env("USERPROFILE")
    if prof:
        bases += [os.path.join(prof, "Desktop"), os.path.join(prof, "OneDrive", "Desktop"),
                  os.path.join(prof, "OneDrive", "Bureau")]
    for var in ("OneDrive", "OneDriveConsumer"):
        if env(var):
            bases += [os.path.join(env(var), "Desktop"), os.path.join(env(var), "Bureau")]
    if env("PUBLIC"):
        bases.append(os.path.join(env("PUBLIC"), "Desktop"))
    if env("APPDATA"):
        bases.append(os.path.join(env("APPDATA"), "Microsoft", "Windows", "Start Menu", "Programs"))
    if env("ProgramData"):
        bases.append(os.path.join(env("ProgramData"), "Microsoft", "Windows", "Start Menu", "Programs"))
    out = []
    for base in bases:
        if not os.path.isdir(base):
            continue
        base_depth = base.rstrip("\\/").count(os.sep)
        for cur, dirs, files in os.walk(base):
            if cur.count(os.sep) - base_depth >= 2:
                dirs[:] = []
            for f in files:
                if not f.lower().endswith(".lnk"):
                    continue
                target = lnk_target(os.path.join(cur, f))
                if os.path.basename(target).lower() in ("ebonhold.exe", "wow.exe"):
                    out.append(os.path.dirname(target))
    return out


def quick_detect(drives=None, use_registry=True, use_shortcuts=True):
    """Candidats trouves sans parcourir les disques (quelques dixiemes de seconde)."""
    drives = fixed_drives() if drives is None else drives
    res = _Results()
    found_dirs = list(_known_dirs(drives))
    if use_registry:
        found_dirs += _registry_dirs()
    if use_shortcuts:
        found_dirs += _shortcut_dirs()
    found_dirs += _shallow_dirs(drives)
    for d in found_dirs:
        res.add_dir(d)
        # Le launcher officiel peut ranger le jeu dans un sous-dossier "Ebonhold".
        res.add_dir(os.path.join(d, "Ebonhold"))
    return res.sorted()


# ---------------------------------------------------------------- scan complet


def _skip(path, name):
    low = name.lower()
    if low in SKIP_NAMES or low.startswith("$"):
        return True
    p = path.replace("/", "\\").lower().rstrip("\\")
    return p.endswith(SKIP_SUFFIXES)


def scan(progress=None, stop_after=90.0, max_depth=6, drives=None, cancel=None,
         include_quick=True):
    """Parcourt les disques fixes et renvoie la liste des Candidats (dedoublonnee, Ebonhold d'abord).

    progress(msg) : appele au plus 5 fois par seconde avec le dossier en cours (anonymise).
    stop_after   : secondes avant arret (les candidats deja trouves sont rendus).
    cancel       : threading.Event optionnel pour interrompre.
    """
    t0 = time.monotonic()
    deadline = t0 + float(stop_after)
    drives = fixed_drives() if drives is None else drives
    res = _Results()
    if include_quick:
        for c in quick_detect(drives):
            res.add_candidate(c)
    last = [0.0]

    def tell(msg, force=False):
        if not progress:
            return
        now = time.monotonic()
        if force or now - last[0] >= 0.2:
            last[0] = now
            try:
                progress(msg)
            except Exception:        # noqa: BLE001 (l'interface ne doit pas casser le scan)
                pass

    # Parcours en largeur : les installs sont en general peu profondes, on les trouve
    # meme si le temps imparti est atteint avant la fin.
    queue = collections.deque((d, 0) for d in drives)
    visited = 0
    stopped = ""
    while queue:
        if cancel is not None and cancel.is_set():
            stopped = " (arrete par le joueur)"
            break
        if time.monotonic() >= deadline:
            stopped = " (arrete : temps ecoule)"
            break
        cur, depth = queue.popleft()
        visited += 1
        tell("Recherche... %s" % anonymize.path(cur))
        try:
            it = os.scandir(cur)
        except OSError:
            continue
        subdirs, has_exe = [], False
        with it:
            for e in it:
                try:
                    if e.is_dir(follow_symlinks=False):
                        if e.is_symlink() or (hasattr(e, "is_junction") and e.is_junction()):
                            continue
                        subdirs.append(e)
                    elif e.name.lower() in EXE_NAMES:
                        has_exe = True
                except OSError:
                    continue
        if has_exe:
            res.add_dir(cur)
            continue            # pas d'autre jeu a l'interieur d'un dossier de jeu
        if depth >= max_depth:
            continue
        for e in subdirs:
            if not _skip(e.path, e.name):
                queue.append((e.path, depth + 1))
    items = res.sorted()
    try:
        from .journal import log
        log("Scan du jeu : %d dossier(s) vus en %.1f s, %d trouve(s)%s"
            % (visited, time.monotonic() - t0, len(items), stopped))
    except Exception:        # noqa: BLE001
        pass
    tell("Recherche terminée : %d dossier(s) trouvé(s)." % len(items), force=True)
    return items
