# -*- coding: utf-8 -*-
"""Signaler un bug / proposer une idee : envoi en issue GitHub dans un depot PRIVE dedie.

Le joueur n'a pas de compte a creer : le launcher envoie avec une cle (jeton GitHub a droits
limites) embarquee au build dans secrets\\report.json, fichier ABSENT du depot git :
    {"repo": "Squall98/Ebonhold-Signalements", "token": "github_pat_...", "branch": "main"}
("branch" facultatif : branche par defaut du depot sinon). Sans ce fichier, l'envoi est
indisponible et l'interface le dit.

Deroulement d'un envoi (send) :
  1. verifications : texte (10 caracteres mini, pas de maximum), pieces jointes (images et videos
     seulement, 25 Mo maxi chacune, 8 maxi), anti-spam (3 envois par heure et par PC) ;
  2. chaque piece jointe est deposee dans le depot sous rapports/<AAAA-MM-JJ>/<id>/<nom> :
     API "contents" (PUT) jusqu'a 10 Mo, au-dela API Git Data (blob + arbre + commit) car
     l'API contents echoue en pratique sur les gros fichiers ("file is too large to be processed") ;
  3. creation de l'issue : texte du joueur + liens/images des pieces jointes + infos du jeu et du
     launcher (bloc depliable) + journal du launcher anonymise (bloc depliable, si accepte).
Le jeton n'apparait JAMAIS dans le journal, les messages ni les exceptions.

Le transport HTTP est injectable (tests) : transport(method, url, headers, body, timeout)
-> (status, headers, body_bytes) ; une erreur reseau leve OSError.
"""
import base64
import http.client
import json
import math
import os
import re
import secrets as _secrets
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

from . import anonymize, gameinfo, paths, secret, version
from .journal import log

API = "https://api.github.com"
KINDS = {
    "bug": {"prefix": "[Bug]", "label": "bug", "word": "Signalement"},
    "suggestion": {"prefix": "[Idée]", "label": "suggestion", "word": "Idee"},
}
EXTRA_LABEL = "launcher"
MIN_TEXT = 10
MAX_FILES = 8
MAX_FILE_SIZE = 25 * 1024 * 1024
CONTENTS_MAX = 10 * 1024 * 1024          # au-dela : API Git Data
IMAGE_EXT = ("png", "jpg", "jpeg", "gif", "bmp", "webp", "tga")
VIDEO_EXT = ("mp4", "webm", "mov", "mkv")
SHOWN_IMAGE_EXT = ("png", "jpg", "jpeg", "gif", "bmp", "webp")    # affichables par un navigateur
CAPTURE_EXT = ("png", "jpg", "jpeg", "tga")
RATE_MAX = 3
RATE_WINDOW = 3600
LOG_LINES = 100
BODY_SAFE = 60000                        # GitHub refuse un corps d'issue > 65 536 caracteres
THUMB_MAX = int(1.5 * 1024 * 1024)
TRIES = 3
TIMEOUT = 30
UPLOAD_TIMEOUT = 90
UNAVAILABLE = "Signalement indisponible dans cette version du launcher."

_LOCK = threading.RLock()
_CONFIG_OVERRIDE = None          # tests : chemin d'un autre report.json
_sleep = time.sleep              # tests : remplace pour ne pas attendre


class ReportError(Exception):
    """Erreur montree au joueur (message en francais, jamais de jeton dedans)."""


# ---------------------------------------------------------------- configuration


def _config_file():
    return _CONFIG_OVERRIDE or paths.resource(os.path.join("secrets", "report.json"))


def load_config():
    """{"repo", "token", "branch"} ou None si la configuration est absente ou invalide."""
    try:
        with open(_config_file(), encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(cfg, dict):
        return None
    repo = str(cfg.get("repo") or "").strip()
    token = str(cfg.get("token") or "").strip()
    if not token and cfg.get("token_x"):          # launcher publie : jeton masque (voir secret.py)
        try:
            token = secret.demasquer(str(cfg["token_x"])).strip()
        except (ValueError, UnicodeDecodeError):
            token = ""
    branch = str(cfg.get("branch") or "").strip()
    if not re.match(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", repo) or len(token) < 20:
        return None
    if branch and not re.match(r"^[A-Za-z0-9_./-]+$", branch):
        branch = ""
    return {"repo": repo, "token": token, "branch": branch}


# ---------------------------------------------------------------- anti-spam


def _rate_file():
    return os.path.join(paths.data_dir(), "reports.json")


def _load_sent():
    try:
        with open(_rate_file(), encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return []
    except (OSError, ValueError):
        try:
            os.replace(_rate_file(), "%s.abime-%d" % (_rate_file(), int(time.time())))
        except OSError:
            pass
        return []
    sent = data.get("sent", []) if isinstance(data, dict) else []
    return [s for s in sent if isinstance(s, dict) and isinstance(s.get("t"), (int, float))]


def _save_sent(sent):
    f = _rate_file()
    tmp = "%s.%d.%d.tmp" % (f, os.getpid(), threading.get_ident())
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"sent": sent}, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, f)


def wait_minutes(now=None):
    """0 si un envoi est possible, sinon minutes a attendre (3 envois par heure et par PC)."""
    now = time.time() if now is None else now
    with _LOCK:
        recent = sorted(s["t"] for s in _load_sent() if now - RATE_WINDOW < s["t"] <= now + 60)
    if len(recent) < RATE_MAX:
        return 0
    free_at = recent[-RATE_MAX] + RATE_WINDOW
    return max(1, int(math.ceil((free_at - now) / 60.0)))


def _record_sent(kind, number, now=None):
    now = time.time() if now is None else now
    with _LOCK:
        sent = [s for s in _load_sent() if now - s["t"] < 24 * 3600]
        sent.append({"t": now, "kind": kind, "number": number})
        try:
            _save_sent(sent)
        except OSError:
            pass


def _rate_message(wait):
    return "Tu as déjà envoyé plusieurs signalements cette heure-ci. Réessaie dans %d min." % wait


# ---------------------------------------------------------------- infos jointes


_EXTRA_LABELS = {
    "launcher_version": "Version du launcher",
    "catalog_source": "Source du catalogue",
    "catalog_version": "Version du catalogue",
    "addons": "Addons installés par le launcher",
    "fr_settings": "Réglages FR",
    "fr_state": "État du patch FR",
    "fr_pack": "Pack FR",
}


def _fmt_value(v):
    if isinstance(v, bool):
        return "oui" if v else "non"
    if v is None:
        return "-"
    if isinstance(v, dict):
        return " ; ".join("%s=%s" % (k, _fmt_value(x)) for k, x in v.items()) or "-"
    if isinstance(v, (list, tuple)):
        return ", ".join(_fmt_value(x) for x in v) or "-"
    return str(v)


def _fmt_item(x):
    name = x.get("name") or x.get("id") or "?"
    ver = x.get("version") or x.get("installed_version") or ""
    rest = ["%s=%s" % (k, _fmt_value(v)) for k, v in x.items()
            if k not in ("name", "id", "version", "installed_version")]
    return "  " + " | ".join([str(name)] + ([str(ver)] if ver else []) + rest)


def format_extra(extra):
    """Section "Launcher" de l'apercu, a partir des infos fournies par l'appelant (api.py)."""
    extra = dict(extra or {})
    extra.setdefault("launcher_version", version.APP_VERSION)
    lines = ["== Launcher =="]
    for k, v in extra.items():
        label = _EXTRA_LABELS.get(k, k)
        if isinstance(v, (list, tuple)) and v and all(isinstance(x, dict) for x in v):
            lines.append("%s : %d" % (label, len(v)))
            lines += [_fmt_item(x) for x in v]
        elif isinstance(v, dict) and v and all(isinstance(x, dict) for x in v.values()):
            lines.append("%s :" % label)
            lines += ["  %s : %s" % (k2, _fmt_value(x)) for k2, x in v.items()]
        else:
            lines.append("%s : %s" % (label, _fmt_value(v)))
    return anonymize.text("\n".join(lines))


def build_infos(kind, wow_path, extra=None):
    """Texte des infos jointes (identique a l'apercu montre au joueur)."""
    info = gameinfo.collect(wow_path, include_logs=(kind == "bug"))
    return format_extra(extra) + "\n\n" + gameinfo.to_text(info)


def _log_file():
    return os.path.join(paths.data_dir(), "launcher.log")


def log_available():
    try:
        return os.path.getsize(_log_file()) > 0
    except OSError:
        return False


def launcher_log_tail(n=LOG_LINES):
    """n dernieres lignes du journal du launcher (et de l'ancien .1 si besoin), anonymisees."""
    lines = gameinfo.tail_lines(_log_file(), n)
    if len(lines) < n:
        lines = gameinfo.tail_lines(_log_file() + ".1", n - len(lines)) + lines
    return [anonymize.text(l) for l in lines]


def info(kind, wow_path, extra=None):
    """Ce que montre la fenetre "Signaler" avant l'envoi.

    -> {"infos_preview": str, "can_send": bool, "wait_minutes": int, "log_available": bool,
        "message": str ("" si tout va bien), "limits": {...}}
    """
    if kind not in KINDS:
        kind = "bug"
    cfg = load_config()
    wait = wait_minutes()
    message = ""
    if not cfg:
        message = UNAVAILABLE
    elif wait:
        message = _rate_message(wait)
    try:
        preview = build_infos(kind, wow_path, extra)
    except Exception as e:        # noqa: BLE001 (l'apercu ne doit jamais bloquer la fenetre)
        log("Signalement : apercu des infos impossible (%s)" % type(e).__name__)
        preview = format_extra(extra) + "\n\n(Infos du jeu indisponibles.)"
    return {"infos_preview": preview, "can_send": bool(cfg) and not wait, "wait_minutes": wait,
            "log_available": log_available(), "message": message,
            "limits": {"min_chars": MIN_TEXT, "max_files": MAX_FILES,
                       "max_file_mb": MAX_FILE_SIZE // (1024 * 1024),
                       "extensions": list(IMAGE_EXT + VIDEO_EXT)}}


# ---------------------------------------------------------------- fichiers (captures, apercus)


def sniff(path):
    """'image', 'video' ou None d'apres les premiers octets (pas seulement l'extension)."""
    try:
        with open(path, "rb") as f:
            head = f.read(32)
    except OSError:
        return None
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    if head.startswith(b"\x89PNG\r\n\x1a\n") or head.startswith(b"\xff\xd8\xff") \
            or head[:6] in (b"GIF87a", b"GIF89a") or (head[:4] == b"RIFF" and head[8:12] == b"WEBP") \
            or (head[:2] == b"BM" and ext == "bmp"):
        return "image"
    if ext == "tga" and len(head) >= 18 and head[1] in (0, 1) and head[2] in (1, 2, 3, 9, 10, 11):
        return "image"
    if head[4:8] in (b"ftyp", b"moov", b"mdat", b"wide", b"free", b"skip") \
            or head.startswith(b"\x1a\x45\xdf\xa3"):
        return "video"
    return None


def _mime(path):
    with open(path, "rb") as f:
        head = f.read(16)
    if head.startswith(b"\x89PNG"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head[:3] == b"GIF":
        return "image/gif"
    if head[:4] == b"RIFF":
        return "image/webp"
    if head[:2] == b"BM":
        return "image/bmp"
    return ""


def _known_folder(guid):
    """Dossier connu de Windows (SHGetKnownFolderPath), ou ''."""
    if os.name != "nt":
        return ""
    try:
        import ctypes
        import uuid
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [("d1", wintypes.DWORD), ("d2", wintypes.WORD), ("d3", wintypes.WORD),
                        ("d4", ctypes.c_ubyte * 8)]
        u = uuid.UUID(guid)
        g = GUID(u.fields[0], u.fields[1], u.fields[2], (ctypes.c_ubyte * 8)(*u.bytes[8:]))
        ptr = ctypes.c_void_p()
        fn = ctypes.windll.shell32.SHGetKnownFolderPath
        fn.argtypes = [ctypes.POINTER(GUID), wintypes.DWORD, wintypes.HANDLE, ctypes.POINTER(ctypes.c_void_p)]
        fn.restype = ctypes.c_long
        if fn(ctypes.byref(g), 0, None, ctypes.byref(ptr)) != 0:
            return ""
        try:
            return ctypes.wstring_at(ptr.value)
        finally:
            ctypes.windll.ole32.CoTaskMemFree(ptr)
    except Exception:        # noqa: BLE001
        return ""


_FOLDERID_SCREENSHOTS = "b7bede81-df94-4682-a7d8-57a52620b86f"
_FOLDERID_PICTURES = "33e28130-4e1e-4676-835a-98395c3bc3bb"
_FOLDERID_VIDEOS = "18989b1d-99b5-455b-841c-ab7c74e4ddfc"


def capture_dirs(wow_path, include_windows=True):
    """Dossiers ou chercher les captures : celui du jeu, puis ceux de Windows."""
    dirs = []
    if wow_path:
        dirs.append(("jeu", os.path.join(wow_path, "Screenshots")))
    if include_windows:
        prof = os.environ.get("USERPROFILE", "")
        pics = _known_folder(_FOLDERID_PICTURES) or (os.path.join(prof, "Pictures") if prof else "")
        vids = _known_folder(_FOLDERID_VIDEOS) or (os.path.join(prof, "Videos") if prof else "")
        cands = [_known_folder(_FOLDERID_SCREENSHOTS)]
        if pics:
            cands += [os.path.join(pics, "Screenshots"), os.path.join(pics, "Captures d’écran"),
                      os.path.join(pics, "Captures d'écran")]
        if vids:
            cands.append(os.path.join(vids, "Captures"))       # Xbox Game Bar (Win+Alt+Impr)
        for od in {os.environ.get("OneDrive", ""), os.environ.get("OneDriveConsumer", ""),
                   os.path.join(prof, "OneDrive") if prof else ""}:
            if od:
                for sub in (("Pictures", "Screenshots"), ("Images", "Screenshots"),
                            ("Images", "Captures d’écran"), ("Images", "Captures d'écran")):
                    cands.append(os.path.join(od, *sub))
        for c in cands:
            if c:
                dirs.append(("windows", c))
    out, seen = [], set()
    for src, d in dirs:
        k = os.path.normcase(os.path.abspath(d))
        if k not in seen and os.path.isdir(d):
            seen.add(k)
            out.append((src, d))
    return out


def recent_captures(wow_path, limit=10, include_windows=True):
    """Les `limit` captures les plus recentes : [{path, name, date, size, size_label, source, mtime}]."""
    items = []
    for src, d in capture_dirs(wow_path, include_windows):
        try:
            entries = list(os.scandir(d))
        except OSError:
            continue
        for e in entries:
            try:
                if not e.is_file() or os.path.splitext(e.name)[1].lower().lstrip(".") not in CAPTURE_EXT:
                    continue
                st = e.stat()
            except OSError:
                continue
            items.append({"path": e.path, "name": e.name, "mtime": st.st_mtime,
                          "date": gameinfo.fmt_date(st.st_mtime), "size": st.st_size,
                          "size_label": gameinfo.fmt_size(st.st_size), "source": src})
    items.sort(key=lambda x: x["mtime"], reverse=True)
    return items[:limit]


def thumbnail(path, max_bytes=THUMB_MAX):
    """Data URL d'une petite image d'apercu, ou None. Ne lit que des fichiers images."""
    try:
        if not path or not os.path.isfile(path):
            return None
        ext = os.path.splitext(path)[1].lower().lstrip(".")
        if ext not in SHOWN_IMAGE_EXT or sniff(path) != "image":
            return None
        size = os.path.getsize(path)
        try:
            from PIL import Image          # facultatif : absent des dependances du launcher
        except ImportError:
            Image = None
        if Image is not None and size > 200 * 1024:
            import io
            with Image.open(path) as im:
                im.thumbnail((320, 320))
                buf = io.BytesIO()
                im.convert("RGB").save(buf, "JPEG", quality=80)
            return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
        if size > max_bytes:
            return None
        mime = _mime(path)
        if not mime:
            return None
        with open(path, "rb") as f:
            return "data:%s;base64,%s" % (mime, base64.b64encode(f.read()).decode("ascii"))
    except Exception:        # noqa: BLE001 (un apercu rate ne doit rien casser)
        return None


# ---------------------------------------------------------------- verifications


def clean_name(name, idx):
    """Nom de fichier sur pour le depot : '1-capture-2026.png' (anonymise, ASCII)."""
    base, ext = os.path.splitext(os.path.basename(str(name)))
    base = anonymize.text(base).replace(anonymize.MASK, "")
    base = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode("ascii")
    base = re.sub(r"[^A-Za-z0-9._-]+", "-", base).strip("-._")[:60] or "fichier"
    ext = re.sub(r"[^a-z0-9]", "", ext.lower())[:5]
    return "%d-%s%s" % (idx, base, ("." + ext) if ext else "")


def _attachment_paths(attachments):
    out = []
    for a in attachments or []:
        p = a.get("path") if isinstance(a, dict) else a
        if p:
            out.append(str(p))
    return out


def validate(kind, text, attachments):
    """'' si tout est bon, sinon le message d'erreur a montrer au joueur."""
    if kind not in KINDS:
        return "Type de signalement inconnu."
    if len((text or "").strip()) < MIN_TEXT:
        return ("Décris le problème en au moins %d caractères." if kind == "bug"
                else "Décris ton idée en au moins %d caractères.") % MIN_TEXT
    paths_ = _attachment_paths(attachments)
    if len(paths_) > MAX_FILES:
        return "%d pièces jointes au maximum (tu en as choisi %d)." % (MAX_FILES, len(paths_))
    seen = set()
    for p in paths_:
        name = os.path.basename(p)
        shown = anonymize.text(name)
        k = os.path.normcase(os.path.abspath(p))
        if k in seen:
            return "%s est joint deux fois." % shown
        seen.add(k)
        ext = os.path.splitext(name)[1].lower().lstrip(".")
        if ext not in IMAGE_EXT + VIDEO_EXT:
            return ("%s : seules les images et les vidéos sont acceptées (%s)."
                    % (shown, ", ".join(IMAGE_EXT + VIDEO_EXT)))
        if not os.path.isfile(p):
            return "%s est introuvable." % shown
        size = os.path.getsize(p)
        if size == 0:
            return "%s est vide." % shown
        if size > MAX_FILE_SIZE:
            return "%s est trop gros (%s, %d Mo maximum)." % (
                shown, gameinfo.fmt_size(size), MAX_FILE_SIZE // (1024 * 1024))
        want = "image" if ext in IMAGE_EXT else "video"
        if sniff(p) != want:
            return "%s n'est pas une %s reconnue." % (shown, want)
    return ""


def precheck(kind, text, attachments):
    """Verification complete avant de lancer l'envoi en arriere-plan : '' ou message d'erreur."""
    err = validate(kind, text, attachments)
    if err:
        return err
    if not load_config():
        return UNAVAILABLE
    wait = wait_minutes()
    return _rate_message(wait) if wait else ""


# ---------------------------------------------------------------- transport HTTP


def urllib_transport(method, url, headers, body, timeout):
    """Transport par defaut (urllib). L'en-tete Authorization n'est jamais transmis en cas de
    redirection (add_unredirected_header)."""
    req = urllib.request.Request(url, data=body, method=method)
    for k, v in headers.items():
        if k.lower() == "authorization":
            req.add_unredirected_header(k, v)
        else:
            req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers.items()), r.read()
    except urllib.error.HTTPError as e:
        try:
            data = e.read()
        except Exception:        # noqa: BLE001
            data = b""
        return e.code, dict(e.headers.items()) if e.headers else {}, data


def _net_reason(e):
    if isinstance(e, TimeoutError) or "timed out" in str(e).lower():
        return "délai dépassé"
    if isinstance(e, urllib.error.URLError):
        return "pas de connexion à Internet ou GitHub injoignable"
    return "connexion interrompue"


class _GitHub:
    def __init__(self, cfg, transport, sleep):
        self.repo = cfg["repo"]
        self._token = cfg["token"]
        self.branch = cfg.get("branch") or ""
        self.transport = transport
        self.sleep = sleep

    def scrub(self, s):
        s = str(s)
        return s.replace(self._token, "***") if self._token else s

    def headers(self):
        return {"Authorization": "Bearer " + self._token,
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "EbonholdLauncher/%s" % version.APP_VERSION,
                "Content-Type": "application/json; charset=utf-8"}

    def call(self, method, path, payload=None, timeout=TIMEOUT, ok=(200, 201), what="",
             retry_409=False):
        """Appel de l'API REST (3 essais sur erreur reseau / 5xx / limite temporaire)."""
        url = API + path
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        err = None
        for attempt in range(TRIES):
            if attempt:
                self.sleep(2 ** attempt)                  # 2 s puis 4 s
            try:
                status, hdrs, data = self.transport(method, url, self.headers(), body, timeout)
            except (OSError, http.client.HTTPException) as e:
                log("Signalement : %s %s -> erreur reseau (%s)" % (method, path, type(e).__name__))
                err = ReportError("Envoi impossible : %s. Réessaie plus tard." % _net_reason(e))
                continue
            if status in ok:
                try:
                    return json.loads(data.decode("utf-8")) if data else {}
                except ValueError:
                    return {}
            msg = self._gh_message(data)
            log("Signalement : %s %s -> HTTP %d %s" % (method, path, status, self.scrub(msg)[:200]))
            hdrs = {k.lower(): v for k, v in (hdrs or {}).items()}
            temporary = status in (500, 502, 503, 504) or (status == 409 and retry_409) or (
                status in (403, 429) and ("secondary rate" in msg.lower() or "retry-after" in hdrs))
            if temporary and attempt < TRIES - 1:
                err = self._error(status, msg, what)
                try:
                    wait = min(float(hdrs.get("retry-after", 0)), 20.0)
                except ValueError:
                    wait = 0
                if wait:
                    self.sleep(wait)
                continue
            raise self._error(status, msg, what)
        raise err or ReportError("Envoi impossible. Réessaie plus tard.")

    @staticmethod
    def _gh_message(data):
        try:
            d = json.loads((data or b"{}").decode("utf-8", "replace"))
        except ValueError:
            return ""
        if not isinstance(d, dict):
            return ""
        parts = [str(d.get("message") or "")]
        for e in d.get("errors") or []:
            if isinstance(e, dict):
                parts.append("%s %s %s" % (e.get("resource", ""), e.get("field", ""),
                                           e.get("code", "") or e.get("message", "")))
            else:
                parts.append(str(e))
        return " | ".join(p for p in parts if p.strip())

    def _error(self, status, msg, what):
        low = msg.lower()
        if status == 401:
            text = "la clé d'envoi du launcher n'est plus valide. Préviens l'équipe sur Discord."
        elif status in (403, 429) and "rate limit" in low:
            text = "GitHub limite les envois pour le moment. Réessaie dans quelques minutes."
        elif status == 403:
            text = "GitHub refuse l'envoi (droits de la clé insuffisants). Préviens l'équipe sur Discord."
        elif status == 404:
            text = "dépôt de signalements introuvable. Préviens l'équipe sur Discord."
        elif status == 409 and "empty" in low:
            text = "le dépôt de signalements est vide (il doit contenir au moins un fichier)."
        elif status in (413, 422) and ("too large" in low or "too big" in low or status == 413):
            text = "%s est trop gros pour GitHub." % (what or "un fichier")
        elif status >= 500:
            text = "GitHub ne répond pas correctement (erreur %d). Réessaie plus tard." % status
        else:
            text = "GitHub a refusé l'envoi (erreur %d)." % status
        e = ReportError("Envoi impossible : " + text)
        e.status = status
        e.gh_message = self.scrub(msg)
        return e

    # -- depot des fichiers

    def put_contents(self, path, data, message, what):
        payload = {"message": message, "content": base64.b64encode(data).decode("ascii")}
        if self.branch:
            payload["branch"] = self.branch
        r = self.call("PUT", "/repos/%s/contents/%s" % (self.repo, urllib.parse.quote(path)), payload,
                      timeout=UPLOAD_TIMEOUT, what=what, retry_409=True)
        c = r.get("content") or {}
        return c.get("html_url") or self.blob_url(path)

    def default_branch(self):
        if not self.branch:
            r = self.call("GET", "/repos/%s" % self.repo, what="le depot")
            self.branch = r.get("default_branch") or "main"
        return self.branch

    def blob_url(self, path):
        return "https://github.com/%s/blob/%s/%s" % (self.repo, urllib.parse.quote(self.branch or "main"),
                                                     urllib.parse.quote(path))

    def put_git(self, files, message, progress=None):
        """Depose plusieurs gros fichiers en UN commit (API Git Data). files = [(path, data, what)]."""
        branch = self.default_branch()
        tree = []
        for i, (path, data, what) in enumerate(files):
            if progress:
                progress(i, what)
            r = self.call("POST", "/repos/%s/git/blobs" % self.repo,
                          {"content": base64.b64encode(data).decode("ascii"), "encoding": "base64"},
                          timeout=UPLOAD_TIMEOUT, what=what)
            tree.append({"path": path, "mode": "100644", "type": "blob", "sha": r["sha"]})
        ref = "/repos/%s/git/refs/heads/%s" % (self.repo, urllib.parse.quote(branch))
        for attempt in range(TRIES):
            head = self.call("GET", "/repos/%s/git/ref/heads/%s" % (self.repo, urllib.parse.quote(branch)),
                             what="la branche")
            parent = head["object"]["sha"]
            commit = self.call("GET", "/repos/%s/git/commits/%s" % (self.repo, parent), what="le commit")
            new_tree = self.call("POST", "/repos/%s/git/trees" % self.repo,
                                 {"base_tree": commit["tree"]["sha"], "tree": tree}, what="l'arbre")
            new_commit = self.call("POST", "/repos/%s/git/commits" % self.repo,
                                   {"message": message, "tree": new_tree["sha"], "parents": [parent]},
                                   what="le commit")
            try:
                self.call("PATCH", ref, {"sha": new_commit["sha"], "force": False}, what="la branche")
                break
            except ReportError as e:
                # 422 "not a fast forward" : quelqu'un a envoye en meme temps, on recommence.
                if getattr(e, "status", 0) != 422 or attempt == TRIES - 1:
                    raise
        return [self.blob_url(p) for p, _d, _w in files]

    def create_issue(self, title, body, labels):
        payload = {"title": title, "body": body, "labels": labels}
        try:
            return self.call("POST", "/repos/%s/issues" % self.repo, payload, what="le signalement")
        except ReportError as e:
            # Etiquettes absentes du depot (ou refusees) : on cree l'issue sans elles.
            if getattr(e, "status", 0) == 422 and "label" in getattr(e, "gh_message", "").lower():
                payload.pop("labels")
                return self.call("POST", "/repos/%s/issues" % self.repo, payload, what="le signalement")
            raise


# ---------------------------------------------------------------- envoi


def _no_mentions(s):
    """Neutralise les @mentions (pas de notification a des inconnus)."""
    return re.sub(r"@(?=[A-Za-z0-9])", "@​", s)


def _fence(s):
    return s.replace("```", "`​``")


def make_title(kind, text):
    first = " ".join((text or "").split())
    if len(first) > 70:
        first = first[:70].rstrip() + "..."
    return _no_mentions("%s %s" % (KINDS[kind]["prefix"], first))


def make_body(kind, text, files, infos, log_lines, full_url=""):
    """Corps Markdown de l'issue. files = [{name, url, size, ext}]."""
    parts = [_no_mentions(text.strip())]
    if full_url:
        parts.append("_Signalement trop long pour GitHub : version complete dans "
                     "[signalement-complet.md](%s)._" % full_url)
    if files:
        lines = ["", "---", "**Pièces jointes (%d)**" % len(files), ""]
        for f in files:
            if f["ext"] in SHOWN_IMAGE_EXT:
                lines.append("![%s](%s?raw=true)" % (f["name"], f["url"]))
            lines.append("- [%s](%s) (%s)" % (f["name"], f["url"], gameinfo.fmt_size(f["size"])))
        parts.append("\n".join(lines))
    parts.append("<details><summary>Infos du jeu et du launcher</summary>\n\n````text\n%s\n````\n</details>"
                 % _fence(infos))
    if log_lines is not None:
        parts.append("<details><summary>Journal du launcher (%d dernières lignes, anonymisé)</summary>\n\n"
                     "````text\n%s\n````\n</details>" % (len(log_lines), _fence("\n".join(log_lines))))
    parts.append("<sub>Envoyé par Ebonhold Launcher %s — %s</sub>" % (version.APP_VERSION, kind))
    return "\n\n".join(parts)


def _shrink(text, n):
    return text if len(text) <= n else text[:n].rstrip() + "\n[... tronque ...]"


def send(kind, text, attachments, include_log, wow_path, extra=None, progress=None,
         transport=None, sleep=None):
    """Envoie le signalement. Bloquant : a lancer dans un thread.

    progress(pct, msg) facultatif. Renvoie
      {"ok": True, "number": 42, "url": "https://github.com/...", "message": "..."}
      ou {"ok": False, "number": None, "url": "", "error": "message pour le joueur"}.
    """
    def tell(pct, msg):
        if progress:
            try:
                progress(int(pct), msg)
            except Exception:        # noqa: BLE001
                pass

    try:
        err = validate(kind, text, attachments)
        if err:
            raise ReportError(err)
        cfg = load_config()
        if not cfg:
            raise ReportError(UNAVAILABLE)
        wait = wait_minutes()
        if wait:
            raise ReportError(_rate_message(wait))
        gh = _GitHub(cfg, transport or urllib_transport, sleep or _sleep)
        tell(2, "Préparation des infos...")
        infos = build_infos(kind, wow_path, extra)
        log_lines = (launcher_log_tail() or None) if include_log else None

        rid = "%s-%s" % (time.strftime("%H%M%S"), _secrets.token_hex(3))
        folder = "rapports/%s/%s" % (time.strftime("%Y-%m-%d"), rid)
        paths_ = _attachment_paths(attachments)
        files, small, big = [], [], []
        for i, p in enumerate(paths_, 1):
            name = clean_name(p, i)
            size = os.path.getsize(p)
            f = {"name": name, "src": p, "size": size, "ext": os.path.splitext(name)[1].lstrip("."),
                 "path": "%s/%s" % (folder, name), "url": ""}
            files.append(f)
            (big if size > CONTENTS_MAX else small).append(f)
        total = sum(f["size"] for f in files) or 1
        done = 0
        commit_msg = "%s %s : pieces jointes" % (KINDS[kind]["word"], rid)
        for f in small:
            tell(5 + 80 * done / total, "Envoi de %s..." % f["name"])
            with open(f["src"], "rb") as fh:
                f["url"] = gh.put_contents(f["path"], fh.read(), commit_msg, f["name"])
            done += f["size"]
        if big:
            datas = []
            for f in big:
                with open(f["src"], "rb") as fh:
                    datas.append((f["path"], fh.read(), f["name"]))

            def big_progress(i, what):
                tell(5 + 80 * (done + sum(b["size"] for b in big[:i])) / total, "Envoi de %s..." % what)
            urls = gh.put_git(datas, commit_msg, big_progress)
            del datas
            for f, u in zip(big, urls):
                f["url"] = u

        tell(88, "Création du signalement...")
        title = make_title(kind, text)
        body = make_body(kind, text, files, infos, log_lines)
        if len(body) > BODY_SAFE:
            # Trop long pour GitHub : version complete deposee a cote, version courte dans l'issue.
            full = body.encode("utf-8")
            full_path = "%s/signalement-complet.md" % folder
            if len(full) > CONTENTS_MAX:
                full_url = gh.put_git([(full_path, full, "le texte complet")], commit_msg)[0]
            else:
                full_url = gh.put_contents(full_path, full, commit_msg, "le texte complet")
            budget = BODY_SAFE - 4000 - 400 * len(files)
            body = make_body(kind, _shrink(text, int(budget * 0.5)), files,
                             _shrink(infos, int(budget * 0.3)),
                             log_lines[-40:] if log_lines else log_lines, full_url=full_url)
            if len(body) > BODY_SAFE:
                body = body[:BODY_SAFE - 200] + "\n\n[... tronque, voir signalement-complet.md ...]"
        labels = [KINDS[kind]["label"], EXTRA_LABEL]
        issue = gh.create_issue(title, body, labels)
        number = issue.get("number")
        if not isinstance(number, int):
            raise ReportError("Envoi incertain : GitHub n'a pas renvoye de numero de signalement.")
        _record_sent(kind, number)
        log("Signalement #%s envoye (%s, %d piece(s) jointe(s), journal %s)"
            % (number, kind, len(files), "oui" if include_log else "non"))
        tell(100, "Envoyé.")
        msg = ("Signalement #%s envoyé, merci !" if kind == "bug" else "Idée #%s envoyée, merci !") % number
        return {"ok": True, "number": number, "url": issue.get("html_url", ""), "message": msg}
    except ReportError as e:
        return {"ok": False, "number": None, "url": "", "error": str(e)}
    except Exception as e:        # noqa: BLE001 (aucun detail technique, et surtout pas le jeton)
        log("Signalement : erreur inattendue %s" % type(e).__name__)
        return {"ok": False, "number": None, "url": "",
                "error": "Envoi impossible : erreur inattendue (%s)." % type(e).__name__}
