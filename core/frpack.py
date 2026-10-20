# -*- coding: utf-8 -*-
"""Installation automatique du pack de langue frFR (~2,4 Go) dans Data\\frFR.

Reprend a la main les etapes du guide (telecharger -> decompresser -> placer le
dossier frFR dans Data) pour que l'utilisateur le fasse en un clic depuis le launcher.

Le pack est decrit dans le manifeste (fr_config.pack_download) sous une de ces formes :
  {"url": "https://.../frFR.zip"}                       # lien direct unique
  {"parts": ["https://.../frFR.zip.001", "...002"]}     # decoupe (contourne la limite 2 Go de GitHub)
  {"url": "https://drive.google.com/file/d/<ID>/view"}  # Google Drive (gros fichier)
Champ "format" optionnel : zip (defaut, recommande), rar, 7z. "sha256" optionnel.

zip = extraction native (fiable). rar/7z = via le tar systeme (libarchive, Win10+),
en best-effort. Recommander le .zip pour la fiabilite.
"""
import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import time
import zipfile

from . import frconfig, wow

PACK_SIZE = 2_600_000_000      # taille approximative du pack (pour verifier la place libre)
_TRIES = 5                     # essais par fichier, avec reprise la ou le telechargement s'est arrete


def _noop(*_):
    pass


# ----------------------------------------------------------------- telechargement

def _drive_id(url):
    m = re.search(r"/file/d/([^/]+)", url) or re.search(r"[?&]id=([^&]+)", url)
    return m.group(1) if m else None


def _onedrive_direct(url):
    """Convertit un lien de partage OneDrive en URL de telechargement direct (sans auth)."""
    import base64
    b64 = base64.urlsafe_b64encode(url.encode("utf-8")).decode("ascii").rstrip("=")
    return "https://api.onedrive.com/v1.0/shares/u!%s/root/content" % b64


def _resolve(url):
    """Transforme un lien de partage cloud en URL de telechargement direct."""
    if "drive.google.com" in url:
        fid = _drive_id(url)
        if not fid:
            raise ValueError("Lien Google Drive non reconnu.")
        return "https://drive.usercontent.google.com/download?id=%s&export=download&confirm=t" % fid
    if "1drv.ms" in url or "onedrive.live.com" in url or "sharepoint.com" in url:
        return _onedrive_direct(url)
    return url


def _download_url(url, dest, progress=_noop, msg="Telechargement"):
    """Telecharge une URL (http direct, Google Drive, OneDrive) ou copie un fichier local."""
    import urllib.request
    url = _resolve(url)

    # Chemin local (ex: V:/.../frFR.zip) ou file:// -> copie directe (utile en dev/offline).
    local = None
    if url.startswith("file://"):
        from urllib.parse import urlparse
        from urllib.request import url2pathname
        local = url2pathname(urlparse(url).path)
    elif "://" not in url and os.path.isabs(url):
        local = url
    if local:
        total = os.path.getsize(local)
        done = 0
        with open(local, "rb") as fin, open(dest, "wb") as fout:
            for chunk in iter(lambda: fin.read(1 << 20), b""):
                fout.write(chunk)
                done += len(chunk)
                progress(int(done * 100 / total) if total else 0, "%s (local)" % msg)
        return dest

    with open(dest, "wb") as out:
        _append_url(url, out, progress, msg)
    return dest


def _append_url(url, out, progress=_noop, msg="Telechargement"):
    """Ajoute le contenu d'une URL a la fin du fichier `out` (ouvert en ecriture binaire).
    Si la connexion coupe, reprend la ou elle s'est arretee (en-tete Range), jusqu'a _TRIES fois."""
    import http.client
    import urllib.error
    import urllib.request
    start = out.tell()
    total = 0
    last_err = None
    for attempt in range(_TRIES):
        done = out.tell() - start
        headers = {"User-Agent": "Mozilla/5.0 EbonholdLauncher"}
        if done:
            headers["Range"] = "bytes=%d-" % done
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=60) as r:
                if done and r.status != 206:      # pas de reprise possible : on recommence ce fichier
                    out.seek(start)
                    out.truncate()
                    done = 0
                length = int(r.headers.get("Content-Length", 0))
                total = done + length if length else total
                for chunk in iter(lambda: r.read(1 << 18), b""):
                    out.write(chunk)
                    done += len(chunk)
                    if total:
                        progress(int(done * 100 / total), "%s %d%%" % (msg, int(done * 100 / total)))
            if total and done < total:
                raise IOError("telechargement incomplet (%d/%d octets)" % (done, total))
            return
        except (OSError, urllib.error.URLError, http.client.HTTPException) as e:
            last_err = e
            out.flush()
            if attempt < _TRIES - 1:
                progress(int(done * 100 / total) if total else 0,
                         "%s : connexion coupee, nouvel essai..." % msg)
                time.sleep(2 * (attempt + 1))
    raise RuntimeError("Telechargement impossible apres %d essais : %s" % (_TRIES, last_err))


def _download_pack_archive(spec, tmpdir, progress=_noop):
    """Telecharge (et reassemble si decoupe) l'archive du pack, directement dans un seul
    fichier (pas de copie intermediaire). Renvoie son chemin."""
    parts = spec.get("parts")
    archive = os.path.join(tmpdir, "frpack.archive")
    if parts:
        with open(archive, "wb") as out:
            for i, purl in enumerate(parts, 1):
                _append_url(_resolve(purl), out, progress, "Partie %d/%d" % (i, len(parts)))
        return archive
    url = spec.get("url")
    if not url:
        raise ValueError("Aucune source de pack (url ou parts) dans le manifeste.")
    return _download_url(url, archive, progress)


def _sha256(path, progress=_noop):
    h = hashlib.sha256()
    total = os.path.getsize(path) or 1
    done = 0
    with open(path, "rb") as f:
        for c in iter(lambda: f.read(1 << 22), b""):
            h.update(c)
            done += len(c)
            progress(int(done * 100 / total), "Verification %d%%" % int(done * 100 / total))
    return h.hexdigest()


def _free_bytes(path):
    try:
        return shutil.disk_usage(path).free
    except OSError:
        return None


def _check_space(tmp, data_dir, size):
    """Le pack passe par le dossier temporaire (archive) puis est extrait dans Data."""
    d_tmp = os.path.splitdrive(os.path.abspath(tmp))[0].upper()
    d_data = os.path.splitdrive(os.path.abspath(data_dir))[0].upper()
    need = {d_tmp: 0, d_data: 0}
    need[d_tmp] += int(size * 1.05)
    need[d_data] += int(size * 1.05)
    for drive, n in need.items():
        free = _free_bytes(tmp if drive == d_tmp else data_dir)
        if free is not None and free < n:
            raise RuntimeError(
                "Pas assez de place sur %s : il faut environ %.1f Go libres, il y en a %.1f. "
                "Libere de la place puis recommence." % (drive or "le disque", n / 1e9, free / 1e9))


# ----------------------------------------------------------------- extraction

def _extract_frfr_zip(archive, data_dir, progress=_noop, log=_noop):
    """Extrait DIRECTEMENT dans Data\\frFR les fichiers du dossier frFR de l'archive (zip),
    sans copie intermediaire. Chaque fichier est ecrit a cote puis renomme : jamais de
    fichier a moitie ecrit a sa place finale. Renvoie False si l'archive n'a pas de frFR."""
    dst_root = os.path.abspath(os.path.join(data_dir, "frFR"))
    with zipfile.ZipFile(archive) as z:
        members = []
        for info in z.infolist():
            parts = info.filename.replace("\\", "/").split("/")
            idx = next((i for i, p in enumerate(parts) if p.lower() == "frfr"), None)
            if idx is None or info.is_dir():
                continue
            rel = [p for p in parts[idx + 1:] if p]
            if not rel or any(p in ("..", ".") for p in rel):
                continue
            members.append((info, os.path.join(dst_root, *rel)))
        if not members:
            return False
        log("Extraction dans Data\\frFR (%d fichiers)..." % len(members))
        total = sum(i.file_size for i, _ in members) or 1
        done = 0
        for info, out in members:
            if not os.path.abspath(out).startswith(dst_root + os.sep):
                raise ValueError("Entree d'archive suspecte : %s" % info.filename)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            part = out + ".partiel"
            with z.open(info) as src, open(part, "wb") as f:
                for c in iter(lambda: src.read(1 << 22), b""):
                    f.write(c)
                    done += len(c)
                    progress(int(done * 100 / total), "Extraction %d%%" % int(done * 100 / total))
            os.replace(part, out)
    log("Dossier frFR place dans Data.")
    return True


def _extract(archive, fmt, dest, log=_noop):
    fmt = (fmt or "zip").lower()
    if fmt == "zip" or zipfile.is_zipfile(archive):
        log("Extraction (zip)...")
        with zipfile.ZipFile(archive) as z:
            z.extractall(dest)
        return
    # rar / 7z : on tente le tar systeme (libarchive sait lire rar/7z sur Win10+).
    log("Extraction (%s) via tar systeme..." % fmt)
    try:
        subprocess.run(["tar", "-xf", archive, "-C", dest], check=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception as e:
        raise RuntimeError(
            "Impossible d'extraire ce format (%s) automatiquement : %s. "
            "Recommande : re-empaqueter le pack en .zip." % (fmt, e))


def _find_frfr(root):
    """Trouve le dossier 'frFR' dans l'arborescence extraite (racine ou imbrique)."""
    if os.path.isdir(os.path.join(root, "frFR")):
        return os.path.join(root, "frFR")
    for cur, dirs, _ in os.walk(root):
        for d in dirs:
            if d.lower() == "frfr":
                return os.path.join(cur, d)
    return None


def _merge_into_data(frfr_src, data_dir, log=_noop):
    dst = os.path.join(data_dir, "frFR")
    os.makedirs(dst, exist_ok=True)
    for name in os.listdir(frfr_src):
        s = os.path.join(frfr_src, name)
        d = os.path.join(dst, name)
        if os.path.isdir(s):
            shutil.copytree(s, d, dirs_exist_ok=True)
        else:
            shutil.copy2(s, d)
    log("Dossier frFR place dans Data.")


# ----------------------------------------------------------------- point d'entree

def install(install_dir, spec, progress=_noop, log=_noop):
    """Telecharge, extrait et installe le pack frFR dans Data. Renvoie True si OK."""
    data_dir = os.path.join(install_dir, "Data")
    if not os.path.isdir(data_dir):
        raise ValueError("Dossier Data introuvable : %s" % data_dir)
    if wow.game_running():
        raise RuntimeError("Ferme d'abord le jeu (Wow.exe), puis recommence.")

    tmp = tempfile.mkdtemp(prefix="ebon-frpack-")
    try:
        _check_space(tmp, data_dir, int(spec.get("size") or PACK_SIZE))
        log("Telechargement du pack frFR (~2,6 Go, ca peut etre long)...")
        archive = _download_pack_archive(spec, tmp, progress)

        sha = spec.get("sha256")
        if sha:
            log("Verification de l'archive...")
            if _sha256(archive, progress).lower() != sha.lower():
                raise ValueError("Archive du pack corrompue (checksum invalide). Recommence l'installation.")

        fmt = (spec.get("format") or "zip").lower()
        if not (zipfile.is_zipfile(archive) and _extract_frfr_zip(archive, data_dir, progress, log)):
            # rar / 7z (ou zip sans dossier frFR reconnu) : ancienne methode, en deux temps.
            extract_dir = os.path.join(tmp, "x")
            os.makedirs(extract_dir)
            _extract(archive, fmt, extract_dir, log)
            frfr = _find_frfr(extract_dir)
            if not frfr:
                raise RuntimeError("Dossier 'frFR' introuvable dans l'archive.")
            _merge_into_data(frfr, data_dir, log)

        if not frconfig.has_pack(data_dir):
            raise RuntimeError("Le pack semble incomplet (locale-frFR.MPQ manquant).")
        log("Pack frFR installe. Tu peux maintenant mettre le Jeu en francais.")
        return True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
