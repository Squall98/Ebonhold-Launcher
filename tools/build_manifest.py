# -*- coding: utf-8 -*-
"""Genere manifest.json a partir des fiches catalog/*.toml + manifest-meta.json.

Pour CHAQUE fiche d'addon (catalog/<id>.toml), on lit la DERNIERE Release GitHub
du repo indique et on en deduit automatiquement :
  - version           (tag de la release, ex v3.1 -> "3.1")
  - download_url       (asset .zip / .mpq de la release)
  - sha256             (calcule en telechargeant l'asset)
  - extract_root       (dossier racine du zip, auto-detecte si non precise)
  - notes / history    (resumes des Releases)
  - changelog_url      (page de la Release)

=> Personne n'edite jamais le JSON ni ne calcule un SHA a la main. Mettre a jour un
   addon = publier une nouvelle Release sur SON repo (le reste est automatique).
   Ajouter un addon = creer une petite fiche catalog/<id>.toml (6 champs).

Les pre-releases et brouillons GitHub sont ignores (releases/latest) : un mod auteur
peut donc tester une build sans qu'elle parte dans le catalogue.

Usage :
  python tools/build_manifest.py            # regenere manifest.json
  python tools/build_manifest.py --strict   # echoue (exit 1) si un addon est invalide (CI)
  python tools/build_manifest.py --only checkpoints   # ne valide qu'une fiche
  python tools/build_manifest.py --check    # n'ecrit rien, montre juste le diff/resultat
"""
import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import tomllib
import urllib.error
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOG_DIR = os.path.join(ROOT, "catalog")
META_FILE = os.path.join(ROOT, "manifest-meta.json")
OUT_FILE = os.path.join(ROOT, "manifest.json")

API = "https://api.github.com"
UA = {"User-Agent": "EbonholdLauncher-catalog-builder"}

# Champs autorises dans une fiche catalog/*.toml (le reste est ignore avec un warning).
KNOWN_KEYS = {
    "id", "name", "repo", "category", "install_target", "extract_root",
    "extract_roots", "filename", "asset", "icon", "accent", "description",
    "long_description", "notes", "order",
}
REQUIRED_KEYS = {"id", "name", "repo", "category", "install_target"}


# --------------------------------------------------------------------------- #
# GitHub helpers (token optionnel : public OK en anonyme, juste rate-limite)
# --------------------------------------------------------------------------- #
def gh_token():
    for var in ("GITHUB_TOKEN", "GH_TOKEN"):
        if os.environ.get(var):
            return os.environ[var]
    try:
        out = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=10)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return None


_TOKEN = None


def api_get(path):
    global _TOKEN
    if _TOKEN is None:
        _TOKEN = gh_token() or ""
    headers = dict(UA)
    headers["Accept"] = "application/vnd.github+json"
    if _TOKEN:
        headers["Authorization"] = "Bearer " + _TOKEN
    req = urllib.request.Request(API + path, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def download(url, dest):
    # Pas d'Authorization ici : browser_download_url redirige vers une URL signee,
    # renvoyer le header casserait certains telechargements.
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
        for chunk in iter(lambda: r.read(1 << 16), b""):
            f.write(chunk)


# --------------------------------------------------------------------------- #
# Petites transformations
# --------------------------------------------------------------------------- #
def strip_v(tag):
    return str(tag or "").strip().lstrip("vV").strip() or str(tag)


def first_line(body, fallback=""):
    """Premiere ligne 'parlante' d'un corps de release (saute les titres markdown)."""
    if not body:
        return fallback
    for raw in body.replace("\r", "").split("\n"):
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        s = re.sub(r"^[-*+]\s+", "", s)        # puce de liste
        s = s.replace("**", "").replace("`", "")  # gras / code inline
        s = re.sub(r"\s+", " ", s).strip()
        if s:
            return s[:200]
    # corps fait uniquement de titres -> prend le premier titre nettoye
    for raw in body.replace("\r", "").split("\n"):
        s = raw.strip().lstrip("#").strip()
        if s:
            return s[:200]
    return fallback


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def zip_root(path):
    with zipfile.ZipFile(path) as z:
        tops = {n.split("/", 1)[0] for n in z.namelist() if n.strip()}
    return next(iter(tops)) if len(tops) == 1 else None


def zip_roots(path):
    """Tous les dossiers racine d'un zip d'addon (gere les addons a plusieurs dossiers,
    ex: GatherMate + GatherMate_Data)."""
    with zipfile.ZipFile(path) as z:
        tops = {n.split("/", 1)[0] for n in z.namelist() if n.strip() and "/" in n}
    return sorted(tops)


def pick_asset(release, fiche):
    """Choisit l'asset a installer dans une release."""
    assets = release.get("assets") or []
    if not assets:
        return None
    if fiche.get("asset"):
        for a in assets:
            if a["name"] == fiche["asset"]:
                return a
        return None
    want = ".mpq" if fiche.get("install_target") == "data" else ".zip"
    for a in assets:
        if a["name"].lower().endswith(want):
            return a
    return assets[0]


# --------------------------------------------------------------------------- #
# Construction d'un produit a partir d'une fiche
# --------------------------------------------------------------------------- #
def build_product(fiche):
    repo = fiche["repo"]
    missing = REQUIRED_KEYS - set(fiche)
    if missing:
        raise ValueError("champs manquants: %s" % ", ".join(sorted(missing)))
    for k in fiche:
        if k not in KNOWN_KEYS and not k.startswith("_"):
            print("  ! champ inconnu ignore: %s" % k)

    latest = api_get("/repos/%s/releases/latest" % repo)
    asset = pick_asset(latest, fiche)
    if not asset:
        raise ValueError("aucun asset .zip/.mpq dans la derniere release de %s" % repo)

    tmp = tempfile.mkdtemp(prefix="ebcat_")
    local = os.path.join(tmp, asset["name"])
    download(asset["browser_download_url"], local)
    sha = sha256_file(local)

    target = fiche["install_target"]
    product = {
        "id": fiche["id"],
        "name": fiche["name"],
        "category": fiche["category"],
        "description": fiche.get("description", ""),
    }
    if fiche.get("long_description"):
        product["long_description"] = fiche["long_description"]
    product["version"] = strip_v(latest["tag_name"])
    product["download_url"] = asset["browser_download_url"]
    product["sha256"] = sha
    product["install_target"] = target

    if target == "addons":
        if fiche.get("extract_roots"):
            roots = list(fiche["extract_roots"])
        elif fiche.get("extract_root"):
            roots = [fiche["extract_root"]]
        else:
            roots = zip_roots(local)
        if not roots:
            raise ValueError("dossier(s) racine du zip indetectable(s) : ajoute extract_root dans la fiche")
        product["extract_root"] = roots[0]
        if len(roots) > 1:
            product["extract_roots"] = roots  # addon a plusieurs dossiers
    else:
        product["filename"] = fiche.get("filename") or asset["name"]

    if fiche.get("icon"):
        product["icon"] = fiche["icon"]
    if fiche.get("accent"):
        product["accent"] = fiche["accent"]

    product["notes"] = fiche.get("notes") or first_line(latest.get("body"), latest.get("name", ""))
    product["changelog_url"] = latest.get("html_url", "https://github.com/%s/releases" % repo)

    # Historique = toutes les releases publiques (hors pre-release/brouillon), 8 max.
    history = []
    try:
        for rel in api_get("/repos/%s/releases?per_page=20" % repo):
            if rel.get("draft") or rel.get("prerelease"):
                continue
            history.append({
                "version": strip_v(rel["tag_name"]),
                "notes": first_line(rel.get("body"), rel.get("name", "")),
            })
            if len(history) >= 8:
                break
    except urllib.error.URLError:
        pass
    if history:
        product["history"] = history

    try:
        os.remove(local)
        os.rmdir(tmp)
    except OSError:
        pass
    return product, asset["name"]


# --------------------------------------------------------------------------- #
def load_fiches(only=None):
    fiches = []
    for fn in sorted(os.listdir(CATALOG_DIR)):
        if not fn.endswith(".toml") or fn.startswith("_"):
            continue
        path = os.path.join(CATALOG_DIR, fn)
        with open(path, "rb") as f:
            data = tomllib.load(f)
        data.setdefault("id", os.path.splitext(fn)[0])
        data["_file"] = fn
        if only and data["id"] != only:
            continue
        fiches.append(data)
    return fiches


def main():
    ap = argparse.ArgumentParser(description="Genere manifest.json depuis catalog/*.toml")
    ap.add_argument("--strict", action="store_true", help="exit 1 si une fiche est invalide (CI)")
    ap.add_argument("--only", help="ne traite qu'une fiche (par id) — pour valider une soumission")
    ap.add_argument("--check", action="store_true", help="n'ecrit pas, montre juste le resultat")
    args = ap.parse_args()

    with open(META_FILE, encoding="utf-8") as f:
        manifest = json.load(f)

    fiches = load_fiches(only=args.only)
    if not fiches:
        print("Aucune fiche catalog/*.toml trouvee%s." % (" pour --only %s" % args.only if args.only else ""))
        if args.strict:
            sys.exit(1)

    products, errors = [], []
    for fiche in fiches:
        fid = fiche.get("id", fiche.get("_file"))
        print("- %s (%s)" % (fid, fiche.get("repo", "?")))
        try:
            product, asset_name = build_product(fiche)
            product["_order"] = fiche.get("order", 100)
            products.append(product)
            print("    v%s  %s  sha256=%s..." % (product["version"], asset_name, product["sha256"][:12]))
        except Exception as e:  # noqa: BLE001 — on veut regrouper toutes les erreurs
            errors.append((fid, str(e)))
            print("    ECHEC: %s" % e)

    products.sort(key=lambda p: (p.pop("_order", 100), p["name"].lower()))

    if args.only:
        # Mode validation d'une seule fiche : ne reecrit pas tout le manifeste.
        if errors:
            print("\nValidation KO: %s" % "; ".join("%s: %s" % e for e in errors))
            sys.exit(1)
        print("\nValidation OK pour: %s" % ", ".join(p["id"] for p in products))
        return

    manifest["products"] = products

    # N'affiche que les categories reellement utilisees (evite un onglet vide).
    used = {p["category"] for p in products}
    defined = {c["id"] for c in manifest.get("categories", [])}
    for cat in sorted(used - defined):
        print("  ! categorie '%s' utilisee mais absente de manifest-meta.json" % cat)
    if "categories" in manifest:
        manifest["categories"] = [c for c in manifest["categories"] if c["id"] in used]

    manifest.setdefault("_generated", True)
    manifest["_source"] = "Genere par tools/build_manifest.py — ne pas editer a la main. Sources: manifest-meta.json + catalog/*.toml"

    new_text = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    old_text = ""
    if os.path.exists(OUT_FILE):
        with io.open(OUT_FILE, encoding="utf-8") as f:
            old_text = f.read()

    changed = new_text != old_text
    print("\n%d addon(s), %d erreur(s). manifest.json: %s" % (
        len(products), len(errors), "MODIFIE" if changed else "inchange"))

    if not args.check:
        if changed:
            with io.open(OUT_FILE, "w", encoding="utf-8") as f:
                f.write(new_text)
            print("-> manifest.json ecrit.")
        else:
            print("-> rien a ecrire.")

    if errors and args.strict:
        sys.exit(1)


if __name__ == "__main__":
    main()
