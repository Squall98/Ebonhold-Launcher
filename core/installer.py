# -*- coding: utf-8 -*-
"""Telechargement, verification et pose des produits dans l'install WoW.

- addon : ZIP extrait dans Interface\\AddOns\\<extract_root>
- patch : .MPQ copie dans Data\\<filename>

Verification d'integrite SHA256 (si fournie dans le manifeste), et rollback :
la cible existante est sauvegardee avant ecriture et restauree si une erreur survient.
"""
import hashlib
import os
import shutil
import tempfile
import zipfile

from . import state, wow


def _noop(_pct, _msg):
    pass


def _is_local(url):
    return url.startswith("file://") or os.path.isabs(url) and "://" not in url


def _local_path(url):
    if url.startswith("file://"):
        from urllib.request import url2pathname
        from urllib.parse import urlparse
        return url2pathname(urlparse(url).path)
    return url


def download(url, dest_path, progress=_noop):
    """Telecharge url -> dest_path (http/https) ou copie un chemin local. Renvoie le SHA256."""
    h = hashlib.sha256()
    if _is_local(url):
        src = _local_path(url)
        total = os.path.getsize(src)
        done = 0
        with open(src, "rb") as fin, open(dest_path, "wb") as fout:
            for chunk in iter(lambda: fin.read(1 << 20), b""):
                fout.write(chunk)
                h.update(chunk)
                done += len(chunk)
                progress(int(done * 100 / total) if total else 0, "Copie...")
        return h.hexdigest()

    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "EbonholdLauncher"})
    with urllib.request.urlopen(req, timeout=30) as r, open(dest_path, "wb") as fout:
        total = int(r.headers.get("Content-Length", 0))
        done = 0
        for chunk in iter(lambda: r.read(1 << 16), b""):
            fout.write(chunk)
            h.update(chunk)
            done += len(chunk)
            progress(int(done * 100 / total) if total else 0, "Telechargement...")
    return h.hexdigest()


def _verify(actual_sha, expected_sha):
    if not expected_sha:
        return  # pas de checksum dans le manifeste -> on n'impose rien
    if actual_sha.lower() != expected_sha.lower():
        raise ValueError("Checksum invalide (fichier corrompu ou altere).")


def install(product, install_dir, progress=_noop):
    """Installe un produit du manifeste. Renvoie la liste des fichiers poses (relatifs a install_dir)."""
    if not wow.is_valid_install(install_dir):
        raise ValueError("Dossier WoW invalide : %s" % install_dir)

    dest_dir = wow.target_dir(install_dir, product["install_target"])
    os.makedirs(dest_dir, exist_ok=True)

    tmp = tempfile.mkdtemp(prefix="ebonhold-dl-")
    backups = []
    try:
        # 1. Telechargement + checksum
        blob = os.path.join(tmp, "payload")
        actual = download(product["download_url"], blob, progress)
        _verify(actual, product.get("sha256"))
        progress(100, "Verifie. Installation...")

        # 2. Pose (avec sauvegarde de l'existant pour rollback)
        if product["install_target"] == "addons":
            # un addon peut poser PLUSIEURS dossiers (ex: GatherMate + GatherMate_Data).
            roots = product.get("extract_roots") or [product["extract_root"]]
            backups = [_backup(os.path.join(dest_dir, r)) for r in roots]
            with zipfile.ZipFile(blob) as z:
                _safe_extract(z, dest_dir)
            rel = [os.path.join("Interface", "AddOns", r) for r in roots]
        else:  # data : copie du MPQ
            fname = product["filename"]
            backups = [_backup(os.path.join(dest_dir, fname))]
            shutil.copy2(blob, os.path.join(dest_dir, fname))
            rel = [os.path.join("Data", fname)]

        state.mark_installed(product["id"], product["version"], rel)
        for b in backups:
            _drop_backup(b)
        progress(100, "Installe.")
        return rel
    except Exception:
        for b in reversed(backups):
            _restore_backup(b)
        raise
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def is_broken(product_id, install_dir):
    """True si le produit est marque installe mais qu'un de ses fichiers manque sur le disque."""
    entry = state.get_installed(product_id)
    if not entry:
        return False
    for rel in entry.get("files", []):
        if not os.path.exists(os.path.join(install_dir, rel)):
            return True
    return False


def uninstall(product_id, install_dir):
    """Supprime les fichiers poses pour un produit, selon l'etat local."""
    entry = state.get_installed(product_id)
    if not entry:
        return
    for rel in entry.get("files", []):
        path = os.path.join(install_dir, rel)
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        elif os.path.exists(path):
            os.remove(path)
    state.mark_removed(product_id)


# ----------------------------------------------------------------- helpers

def _safe_extract(zf, dest_dir):
    """Extraction Zip avec garde anti 'Zip Slip' (chemins ../ hors du dossier cible)."""
    dest_abs = os.path.abspath(dest_dir)
    for member in zf.namelist():
        out = os.path.abspath(os.path.join(dest_dir, member))
        if not (out == dest_abs or out.startswith(dest_abs + os.sep)):
            raise ValueError("Entree d'archive suspecte : %s" % member)
    zf.extractall(dest_dir)


def _backup(target):
    """Renomme une cible existante en .bak ; renvoie le chemin du backup ou None."""
    if os.path.exists(target):
        bak = target + ".launcher-bak"
        if os.path.exists(bak):
            if os.path.isdir(bak):
                shutil.rmtree(bak, ignore_errors=True)
            else:
                os.remove(bak)
        os.rename(target, bak)
        return (target, bak)
    return None


def _restore_backup(backup):
    if not backup:
        return
    target, bak = backup
    if os.path.exists(target):
        if os.path.isdir(target):
            shutil.rmtree(target, ignore_errors=True)
        else:
            os.remove(target)
    if os.path.exists(bak):
        os.rename(bak, target)


def _drop_backup(backup):
    if not backup:
        return
    _, bak = backup
    if os.path.isdir(bak):
        shutil.rmtree(bak, ignore_errors=True)
    elif os.path.exists(bak):
        os.remove(bak)
