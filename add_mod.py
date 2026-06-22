# -*- coding: utf-8 -*-
"""Ajoute (ou met a jour) un mod dans manifest.json — sans editer le JSON a la main.

Calcule le SHA256, devine le dossier racine d'un ZIP d'addon, et insere l'entree.
Si un produit avec le meme --id existe deja, il est mis a jour (pratique pour une
nouvelle version : il suffit de relancer avec le nouveau --file et --version).

Exemples
--------
Addon (ZIP) :
  python add_mod.py --id atlasloot --name "AtlasLoot" --category interface --target addons --version 1.0 \\
      --file "V:/Project/Ebonhold/releases/AtlasLoot-v1.0.zip" \\
      --icon ti-map --accent blue --desc "Tables de butin des donjons."

Patch (MPQ) :
  python add_mod.py --id patch-w --name "Patch W (sons)" --category donnees --target data --version 1.0 \\
      --file "V:/Project/Ebonhold/database/patch-W.MPQ" --icon ti-music --accent amber

Le --category est libre (id d'une categorie du manifeste). Le --target decide ou vont les fichiers.

En prod, ajoute --url https://github.com/.../releases/download/... pour pointer la release
GitHub au lieu du fichier local (le SHA256 reste celui du --file fourni).
"""
import argparse
import hashlib
import json
import os
import sys
import zipfile

ACCENTS = ["purple", "teal", "coral", "blue", "amber", "pink", "green"]
MANIFEST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "manifest.json")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def zip_root(path):
    """Devine le dossier racine commun d'un ZIP d'addon (ex: 'EbonholdFR')."""
    with zipfile.ZipFile(path) as z:
        tops = {n.split("/", 1)[0] for n in z.namelist() if n.strip()}
    if len(tops) == 1:
        return next(iter(tops))
    return None


def main():
    ap = argparse.ArgumentParser(description="Ajoute/MAJ un mod dans manifest.json")
    ap.add_argument("--id", required=True, help="identifiant unique (kebab-case)")
    ap.add_argument("--name", required=True)
    ap.add_argument("--category", required=True,
                    help="id de categorie d'affichage (libre, ex: traduction, interface, donnees)")
    ap.add_argument("--target", required=True, choices=["addons", "data"],
                    help="ou poser les fichiers: addons (Interface\\AddOns) ou data (Data)")
    ap.add_argument("--version", required=True)
    ap.add_argument("--file", required=True, help="chemin du ZIP (addons) ou .MPQ (data)")
    ap.add_argument("--url", help="download_url public (defaut: chemin local du --file)")
    ap.add_argument("--extract-root", help="addons: dossier racine du ZIP (auto-detecte sinon)")
    ap.add_argument("--filename", help="data: nom du fichier dans Data (defaut: basename du --file)")
    ap.add_argument("--icon", default="", help="icone Tabler, ex: ti-shield")
    ap.add_argument("--accent", default="", choices=[""] + ACCENTS, help="couleur de carte")
    ap.add_argument("--desc", default="")
    ap.add_argument("--changelog", default="")
    args = ap.parse_args()

    if not os.path.isfile(args.file):
        sys.exit("Fichier introuvable: %s" % args.file)

    entry = {
        "id": args.id,
        "name": args.name,
        "category": args.category,
        "description": args.desc,
        "version": args.version,
        "download_url": args.url or os.path.abspath(args.file).replace("\\", "/"),
        "sha256": sha256(args.file),
        "install_target": args.target,
    }
    if args.target == "addons":
        root = args.extract_root or zip_root(args.file)
        if not root:
            sys.exit("Impossible de deviner le dossier racine du ZIP : precise --extract-root.")
        entry["extract_root"] = root
    else:
        entry["filename"] = args.filename or os.path.basename(args.file)
    if args.icon:
        entry["icon"] = args.icon
    if args.accent:
        entry["accent"] = args.accent
    if args.changelog:
        entry["changelog_url"] = args.changelog

    with open(MANIFEST, encoding="utf-8") as f:
        manifest = json.load(f)
    products = manifest.setdefault("products", [])

    for i, p in enumerate(products):
        if p.get("id") == args.id:
            products[i] = entry
            action = "mis a jour"
            break
    else:
        products.append(entry)
        action = "ajoute"

    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print("Mod '%s' %s dans manifest.json (sha256=%s...)" % (args.id, action, entry["sha256"][:12]))


if __name__ == "__main__":
    main()
