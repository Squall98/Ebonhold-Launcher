# Ajouter ou mettre à jour un addon dans le launcher Ebonhold

Le catalogue du launcher (le `manifest.json` que voient les joueurs) est **généré
automatiquement**. Personne n'édite ce fichier à la main et **personne ne calcule de
SHA256** : un robot lit la dernière *Release* GitHub de chaque mod et remplit tout seul la
version, le lien de téléchargement, l'empreinte SHA256 et l'historique.

> Règle d'or : **chaque addon a son propre dépôt GitHub**, et on publie ses versions avec
> les *Releases* de ce dépôt.

---

## 🔁 Mettre à jour un addon (le plus fréquent)

Tu n'as **rien** à faire sur le launcher.

1. Sur le dépôt de **ton** addon, publie une nouvelle **Release** (ex. `v1.3`) avec le `.zip`
   en pièce jointe.
2. C'est tout. Le catalogue se met à jour tout seul (dans les ~2 h, ou tout de suite si un
   admin clique sur *Run workflow* → « Régénère le catalogue »).

> 💡 Une build pas prête ? Coche **« pre-release »** sur la Release GitHub : elle sera ignorée
> par le catalogue tant qu'elle reste en pre-release.

---

## ➕ Ajouter un nouvel addon

Deux façons, au choix. **Aucune des deux ne demande de toucher au JSON.**

### Option A — Le formulaire (le plus simple)

1. Onglet **Issues** du dépôt → **New issue** → **« ➕ Ajouter un addon au launcher »**.
2. Remplis les champs (repo du mod, nom, catégorie, description…). Valide.
3. Un robot vérifie le dépôt et **ouvre une Pull Request** tout seul. Un admin la relit et la
   merge. Terminé.

### Option B — Le petit fichier (pour les habitués de GitHub)

1. Copie [`catalog/_TEMPLATE.toml`](catalog/_TEMPLATE.toml) en `catalog/<id>.toml`
   (ex. `catalog/atlasloot.toml`) — le plus simple : bouton **Add file → Create new file**.
2. Remplis les ~8 champs (voir le modèle).
3. **Propose changes** → ça crée une Pull Request. Un admin la merge.

---

## Les champs d'une fiche

| Champ | Obligatoire | Rôle |
|---|---|---|
| `id` | ✅ | identifiant unique en minuscules/tirets (= nom du fichier) |
| `name` | ✅ | nom affiché sur la carte |
| `repo` | ✅ | `owner/repo` GitHub où sont publiées les Releases |
| `category` | ✅ | `traduction`, `interface` ou `donnees` |
| `install_target` | ✅ | `addons` (→ `Interface\AddOns`) ou `data` (→ `Data`) |
| `extract_root` | — | dossier racine **dans le zip** (auto-détecté si vide) |
| `icon` | — | icône [Tabler](https://tabler.io/icons), ex. `ti-map-pin` |
| `accent` | — | `purple`, `teal`, `coral`, `blue`, `amber`, `pink`, `green` |
| `order` | — | ordre d'affichage (petit = en premier) |
| `description` | ✅ | phrase courte (carte) |
| `long_description` | — | texte de la fiche détaillée |
| `notes` | — | force le texte « Nouveautés » (défaut : 1re ligne de la Release) |

La **version**, le **lien**, le **SHA256**, le **changelog** et l'**historique** ne se
renseignent **pas** : ils viennent de la dernière Release du `repo`.

---

## Qui peut faire quoi

- **Tout le monde** (avec un compte GitHub) peut **proposer** un addon : ça crée une PR.
- Un **admin** relit puis **merge** la PR → l'addon part dans le catalogue.
- Les **mises à jour de version** sont automatiques (publier une Release suffit).

## Pour les admins — tester en local

```bash
python tools/build_manifest.py          # régénère manifest.json depuis les sources
python tools/build_manifest.py --check   # montre le résultat sans rien écrire
python tools/build_manifest.py --only <id> --strict   # valide une seule fiche
```

Sources du catalogue : [`manifest-meta.json`](manifest-meta.json) (partie globale, admin
uniquement) + [`catalog/*.toml`](catalog/) (un fichier par addon). **Ne jamais éditer
`manifest.json` à la main** : il est régénéré.
