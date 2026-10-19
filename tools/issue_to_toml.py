# -*- coding: utf-8 -*-
"""Transforme une soumission du formulaire 'Ajouter un addon' en fiche catalog/<id>.toml.

Lit le corps de l'issue (env ISSUE_BODY), genere la fiche TOML, et ecrit l'id de l'addon
dans GITHUB_OUTPUT (cle: id) pour la suite du workflow. Aucune dependance externe.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOG_DIR = os.path.join(ROOT, "catalog")

# Libelle du champ du formulaire -> cle de la fiche. Doit suivre add-addon.yml.
LABEL_TO_KEY = {
    "Repo GitHub du mod": "repo",
    "Identifiant unique": "id",
    "Nom affiché": "name",
    "Catégorie": "category",
    "Destination des fichiers": "install_target",
    "Dossier racine du zip (addons)": "extract_root",
    "Icône (Tabler)": "icon",
    "Couleur de la carte": "accent",
    "Description courte": "description",
    "Description longue": "long_description",
}
ORDER = ["id", "name", "repo", "category", "install_target", "extract_root",
         "icon", "accent", "order", "description", "long_description"]
EMPTY = {"", "_No response_", "_Aucune réponse_", "None"}
# Champs d'une seule ligne : le texte de l'issue est libre (n'importe qui peut l'editer),
# on n'en garde qu'une ligne, sans caractere de controle.
ONE_LINE = ("repo", "id", "name", "category", "install_target", "extract_root", "icon", "accent")
ACCENTS = {"purple", "teal", "coral", "blue", "amber", "pink", "green"}
META_FILE = os.path.join(ROOT, "manifest-meta.json")


def categories():
    try:
        import json
        with open(META_FILE, encoding="utf-8") as f:
            return {c["id"] for c in json.load(f).get("categories", [])}
    except (OSError, ValueError, KeyError):
        return set()


def parse_issue_form(body):
    """Decoupe un corps d'issue-form GitHub (### Libelle\\n\\nvaleur) en dict."""
    fields, current, buf = {}, None, []

    def flush():
        if current is not None:
            val = "\n".join(buf).strip()
            key = LABEL_TO_KEY.get(current)
            if key and val not in EMPTY:
                fields[key] = val

    for line in body.replace("\r", "").split("\n"):
        m = re.match(r"^###\s+(.*?)\s*$", line)
        if m:
            flush()
            current, buf = m.group(1), []
        else:
            buf.append(line)
    flush()
    return fields


def toml_str(value):
    value = re.sub(r"\s+", " ", value).strip()
    value = value.replace("\\", "\\\\").replace('"', '\\"')
    return '"%s"' % value


def main():
    body = os.environ.get("ISSUE_BODY", "")
    if not body.strip():
        sys.exit("ISSUE_BODY vide.")

    f = parse_issue_form(body)
    for k in ONE_LINE:
        if k in f:
            f[k] = re.sub(r"[\x00-\x1f\x7f]+", " ", f[k]).strip()

    # Normalise le repo : accepte une URL GitHub complète (avec ou sans / final, .git)
    # autant que le format court 'owner/repo'.
    repo = f.get("repo", "").strip()
    m = re.search(r"github\.com[/:]([^/\s]+/[^/\s]+?)(?:\.git)?/?$", repo)
    if m:
        repo = m.group(1)
    repo = repo.strip().rstrip("/")
    if repo:
        f["repo"] = repo

    # Validations.
    errors = []
    fid = f.get("id", "")
    if not re.match(r"^[a-z0-9][a-z0-9-]*$", fid):
        errors.append("Identifiant invalide (minuscules, chiffres et tirets uniquement) : '%s'" % fid)
    if not re.match(r"^[\w.-]+/[\w.-]+$", f.get("repo", "")):
        errors.append("Repo invalide, attendu 'owner/repo' : '%s'" % f.get("repo", ""))
    # Un patch .mpq (destination Data) peut remplacer n'importe quel fichier du jeu :
    # reserve a l'admin (fiche ecrite a la main), jamais via le formulaire public.
    if f.get("install_target") != "addons":
        errors.append("Destination invalide : '%s' (le formulaire n'accepte que 'addons')" % f.get("install_target", ""))
    for req in ("name", "category", "description"):
        if not f.get(req):
            errors.append("Champ requis manquant : %s" % req)
    name = f.get("name", "")
    if len(name) > 60 or re.search(r'[<>"`$\\]', name):
        errors.append("Nom invalide (60 caracteres max, sans < > \" ` $ \\) : '%s'" % name[:60])
    cats = categories()
    if cats and f.get("category") and f["category"] not in cats:
        errors.append("Categorie inconnue : '%s'" % f["category"])
    if f.get("extract_root") and not re.match(r"^[A-Za-z0-9_.-]+$", f["extract_root"]):
        errors.append("Dossier racine invalide : '%s'" % f["extract_root"])
    if f.get("icon") and not re.match(r"^ti-[a-z0-9-]+$", f["icon"]):
        errors.append("Icone invalide (format ti-nom) : '%s'" % f["icon"])
    if f.get("accent") and f["accent"] not in ACCENTS:
        errors.append("Couleur invalide : '%s'" % f["accent"])
    if errors:
        sys.exit("Formulaire invalide :\n- " + "\n- ".join(errors))

    # Construit le contenu TOML.
    lines = ["# Fiche generee depuis le formulaire GitHub. Voir catalog/_TEMPLATE.toml.",
             "# Version / lien / SHA256 viennent automatiquement de la derniere Release du repo.",
             ""]
    for key in ORDER:
        if key in f:
            lines.append("%s = %s" % (key, toml_str(f[key])))

    os.makedirs(CATALOG_DIR, exist_ok=True)
    path = os.path.join(CATALOG_DIR, "%s.toml" % fid)
    with open(path, "w", encoding="utf-8") as out:
        out.write("\n".join(lines) + "\n")

    print("Fiche ecrite : catalog/%s.toml" % fid)
    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        # Valeurs deja validees ci-dessus : une seule ligne chacune, impossible d'ajouter
        # une autre cle (ex: redefinir 'id') dans GITHUB_OUTPUT.
        with open(gh_out, "a", encoding="utf-8") as o:
            o.write("id=%s\n" % fid)
            o.write("name=%s\n" % name)


if __name__ == "__main__":
    main()
