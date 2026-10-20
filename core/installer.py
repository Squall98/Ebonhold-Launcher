# -*- coding: utf-8 -*-
"""Telechargement, verification et pose des produits dans l'install WoW.

- addon : ZIP extrait dans Interface\\AddOns\\<extract_root>
- patch : .MPQ copie dans Data\\<filename>

Verification d'integrite SHA256 (si fournie dans le manifeste), et rollback :
la cible existante est sauvegardee avant ecriture et restauree si une erreur survient.
"""
import hashlib
import os
import re
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

    import http.client
    import time
    import urllib.error
    import urllib.request
    last_err = None
    for attempt in range(3):          # petits fichiers : en cas de coupure, on recommence
        h = hashlib.sha256()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "EbonholdLauncher"})
            with urllib.request.urlopen(req, timeout=30) as r, open(dest_path, "wb") as fout:
                total = int(r.headers.get("Content-Length", 0))
                done = 0
                for chunk in iter(lambda: r.read(1 << 16), b""):
                    fout.write(chunk)
                    h.update(chunk)
                    done += len(chunk)
                    progress(int(done * 100 / total) if total else 0, "Téléchargement...")
            if total and done < total:
                raise IOError("telechargement incomplet")
            return h.hexdigest()
        except urllib.error.HTTPError as e:
            if e.code < 500:              # 404, 403... : inutile de reessayer
                raise RuntimeError("Fichier introuvable sur le serveur (HTTP %d)." % e.code)
            last_err = e
        except (OSError, urllib.error.URLError, http.client.HTTPException) as e:
            last_err = e
        time.sleep(1.5 * (attempt + 1))
    raise RuntimeError("Téléchargement impossible : %s" % last_err)


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
        progress(100, "Vérifié. Installation...")

        # 2. Pose (avec sauvegarde de l'existant pour rollback)
        if product["install_target"] == "addons":
            # un addon peut poser PLUSIEURS dossiers (ex: GatherMate + GatherMate_Data).
            roots = product.get("extract_roots") or [product["extract_root"]]
            for r in roots:
                if _reserved(r):
                    raise ValueError("Dossier reserve au jeu ou au serveur : %s" % r)
            with zipfile.ZipFile(blob) as z:
                present = _zip_roots(z)
                missing = [r for r in roots if r.lower() not in present]
                if missing:
                    raise ValueError("Archive inattendue : dossier %s absent du zip." % ", ".join(missing))
                backups = [_backup(os.path.join(dest_dir, r)) for r in roots]
                # Seuls les dossiers declares de l'addon sont extraits : jamais un autre
                # addon, ni un dossier du jeu ou du serveur glisse dans le zip.
                _safe_extract(z, dest_dir, roots)
            rel = [os.path.join("Interface", "AddOns", r) for r in roots]
        else:  # data : copie du MPQ
            fname = product["filename"]
            backups = [_backup(os.path.join(dest_dir, fname))]
            shutil.copy2(blob, os.path.join(dest_dir, fname))
            rel = [os.path.join("Data", fname)]

        state.mark_installed(product["id"], product["version"], rel)
        for b in backups:
            _drop_backup(b)
        progress(100, "Installé.")
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


def _toc_version(path):
    """Lit la ligne '## Version:' d'un .toc d'addon. Renvoie '' si absent/illisible."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                m = re.search(r"##\s*Version:\s*(.+)", line)
                if m:
                    return m.group(1).strip()
    except OSError:
        pass
    return ""


def disk_version(product, install_dir):
    """Detecte un addon DEJA present dans Interface\\AddOns mais non installe par le launcher.

    Renvoie sa version (lue dans le .toc), '' si present mais version illisible, ou None s'il
    n'est pas (completement) present. Addons seulement (pas les patchs data)."""
    if product.get("install_target") != "addons":
        return None
    roots = product.get("extract_roots") or ([product["extract_root"]] if product.get("extract_root") else [])
    if not roots:
        return None
    addons = wow.addons_dir(install_dir)
    for r in roots:
        if not os.path.isdir(os.path.join(addons, r)):
            return None
    primary = roots[0]
    return _toc_version(os.path.join(addons, primary, primary + ".toc"))


def uninstall(product_id, install_dir, product=None):
    """Supprime les fichiers d'un produit. Selon l'etat local s'il a ete installe par le
    launcher ; sinon (addon present sur disque mais non suivi) selon ses dossiers du manifeste."""
    entry = state.get_installed(product_id)
    if entry:
        rels = entry.get("files", [])
    elif product and product.get("install_target") == "addons":
        roots = product.get("extract_roots") or ([product["extract_root"]] if product.get("extract_root") else [])
        rels = [os.path.join("Interface", "AddOns", r) for r in roots]
    else:
        return
    for rel in rels:
        path = os.path.join(install_dir, rel)
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        elif os.path.exists(path):
            os.remove(path)
    state.mark_removed(product_id)


# ----------------------------------------------------------------- helpers

def _reserved(root):
    """Dossiers qu'un addon du catalogue ne doit jamais remplacer : addon du serveur,
    interface Blizzard, correctif FR pose par le launcher."""
    r = str(root).lower()
    return r == "projectebonhold" or r.startswith("blizzard_") or r == "ebonholdfrfix"


def _zip_roots(zf):
    return {n.replace("\\", "/").split("/", 1)[0].lower()
            for n in zf.namelist() if "/" in n.replace("\\", "/")}


def _safe_extract(zf, dest_dir, roots=None):
    """Extraction Zip avec garde anti 'Zip Slip' (chemins ../ hors du dossier cible).
    Si `roots` est donne, n'extrait que les entrees de ces dossiers racine."""
    dest_abs = os.path.abspath(dest_dir)
    wanted = {r.lower() for r in roots} if roots else None
    members = []
    for member in zf.namelist():
        top = member.replace("\\", "/").split("/", 1)[0].lower()
        if wanted is not None and top not in wanted:
            continue
        out = os.path.abspath(os.path.join(dest_dir, member))
        if not (out == dest_abs or out.startswith(dest_abs + os.sep)):
            raise ValueError("Entree d'archive suspecte : %s" % member)
        members.append(member)
    zf.extractall(dest_dir, members=members)


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
