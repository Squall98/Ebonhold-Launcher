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
import os
import re
import shutil
import subprocess
import tempfile
import zipfile

from . import frconfig


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

    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 EbonholdLauncher"})
    with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as f:
        total = int(r.headers.get("Content-Length", 0))
        done = 0
        for chunk in iter(lambda: r.read(1 << 18), b""):
            f.write(chunk)
            done += len(chunk)
            if total:
                progress(int(done * 100 / total), "%s %d%%" % (msg, int(done * 100 / total)))
    return dest


def _download_pack_archive(spec, tmpdir, progress=_noop):
    """Telecharge (et reassemble si decoupe) l'archive du pack. Renvoie son chemin."""
    parts = spec.get("parts")
    archive = os.path.join(tmpdir, "frpack.archive")
    if parts:
        with open(archive, "wb") as out:
            for i, purl in enumerate(parts, 1):
                p = os.path.join(tmpdir, "part%d" % i)
                _download_url(purl, p, progress, "Partie %d/%d" % (i, len(parts)))
                with open(p, "rb") as f:
                    shutil.copyfileobj(f, out)
                os.remove(p)
        return archive
    url = spec.get("url")
    if not url:
        raise ValueError("Aucune source de pack (url ou parts) dans le manifeste.")
    return _download_url(url, archive, progress)


# ----------------------------------------------------------------- extraction

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

    tmp = tempfile.mkdtemp(prefix="ebon-frpack-")
    try:
        log("Telechargement du pack frFR (~2,4 Go, ca peut etre long)...")
        archive = _download_pack_archive(spec, tmp, progress)

        sha = spec.get("sha256")
        if sha:
            import hashlib
            h = hashlib.sha256()
            with open(archive, "rb") as f:
                for c in iter(lambda: f.read(1 << 20), b""):
                    h.update(c)
            if h.hexdigest().lower() != sha.lower():
                raise ValueError("Archive du pack corrompue (checksum invalide).")

        extract_dir = os.path.join(tmp, "x")
        os.makedirs(extract_dir)
        _extract(archive, spec.get("format"), extract_dir, log)

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
