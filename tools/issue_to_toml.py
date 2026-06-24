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
    if f.get("install_target") not in ("addons", "data"):
        errors.append("Destination invalide : '%s'" % f.get("install_target", ""))
    for req in ("name", "category", "description"):
        if not f.get(req):
            errors.append("Champ requis manquant : %s" % req)
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
        with open(gh_out, "a", encoding="utf-8") as o:
            o.write("id=%s\n" % fid)
            o.write("name=%s\n" % f.get("name", fid))


if __name__ == "__main__":
    main()
