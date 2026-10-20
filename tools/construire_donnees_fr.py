# -*- coding: utf-8 -*-
"""Construit la base de traductions unique du patch FR : vendor/patch_fr.json.

Entrees (chemins en arguments, voir --help) :
  - la base historique {names, descs} (cle = texte anglais exact du serveur) ;
  - des traductions supplementaires au meme format (ex. trad/dbc-fr.json), prioritaires ;
  - la capture anglaise du jeu (EbonholdEchoDump, SavedVariables) pour les categories de sorts.

Sortie : {version, genere, categories{echo,soultree,affix,tome}, names, descs, noms_dans_desc}
ou noms_dans_desc[desc_anglaise] = [[nom_anglais, nom_francais, forme_avec_article|null], ...]
permet au launcher de remettre les noms Ebonhold en anglais dans les descriptions francaises
quand le joueur garde les noms en anglais.

  python tools/construire_donnees_fr.py --base vendor/custom_translations.json \
      --plus ../chantier-maj-2026-10/trad/dbc-fr.json --capture <EbonholdEchoDump-enUS.lua> \
      --sortie vendor/patch_fr.json --version 4.0
"""
import argparse
import datetime
import json
import os
import re
import sys

TOKENS = re.compile(r"\$[A-Za-z0-9{}*/.+-]+|@[^@]*@|%[sd]")


def lire_json(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def categories_depuis_capture(chemin):
    """IDs des echoes, sorts du Soul Tree, affixes et tomes, lus dans la capture du jeu."""
    try:
        from lupa import luajit21 as L
    except ImportError:
        sys.exit("lupa est necessaire pour lire la capture (pip install lupa)")
    lua = L.LuaRuntime()
    with open(chemin, encoding="utf-8", errors="replace") as f:
        lua.execute(f.read())
    db = lua.globals().EchoDumpDB
    out, noms = {}, set()
    for cat, cle in (("echo", "perks"), ("soultree", "skilltree"), ("affix", "affixes"), ("tome", "tomes")):
        t = db[cle]
        out[cat] = sorted(int(k) for k in t.keys()) if t is not None else []
        for k in (t.keys() if t is not None else []):
            n = t[k]["name"]
            if n:
                noms.add(re.sub(r"\s*\((?:Rank|Rang) \d+\)$", "", str(n)).strip())
    return out, noms


ARTICLES = ("le ", "la ", "les ", "l'", "l’", "du ", "des ", "de la ", "de l'", "au ", "aux ")
RANG = re.compile(r"\s*\((?:Rank|Rang) \d+\)$")
REMPLACE_EN = re.compile(r"Replace (.+?) \(Rank (\d+)\)\.?\s*$")
REMPLACE_FR = re.compile(r"Remplace\b[^\r\n]*$")


def _nom_fr_rang(names, nom, rang):
    for n in (nom, nom.replace("’", "'"), nom.replace("'", "’")):
        fr = names.get("%s (Rank %s)" % (n, rang))
        if fr:
            return fr
    for n in (nom, nom.replace("’", "'"), nom.replace("'", "’")):
        if names.get(n):
            return "%s (Rang %s)" % (names[n], rang)
    return "%s (Rang %s)" % (nom, rang)


def normaliser_remplace(names, descs):
    """« Replace <noeud> (Rank N). » en fin de description : meme nom francais que la table
    des noms (sinon Rang/Niveau et noms melanges selon le traducteur, ex. « Exécuteur's Oath »)."""
    n = 0
    for en, fr in list(descs.items()):
        m = REMPLACE_EN.search(en)
        if not m:
            continue
        cible = "Remplace %s." % _nom_fr_rang(names, m.group(1), m.group(2))
        if REMPLACE_FR.search(fr):
            nouveau = REMPLACE_FR.sub(lambda _: cible, fr)
        else:
            nouveau = fr.rstrip() + ("\r\n\r\n" if "\r\n" in fr else "\n\n") + cible
        if nouveau != fr:
            descs[en] = nouveau
            n += 1
    return n


def noms_dans_desc(names, descs, noms_ebonhold):
    """Pour chaque description : les noms Ebonhold (anglais -> francais) qu'elle cite.
    Seulement les noms d'echoes, de noeuds, d'affixes et de tomes (jamais un sort Blizzard
    ni un mot courant comme « Shadow » : « dégâts d'Ombre » doit rester tel quel).
    Un nom avec son rang (« Lifebond (Rank 4) ») est assez precis pour etre gardé meme en un mot."""
    paires = [(en, fr) for en, fr in names.items()
              if RANG.sub("", en) in noms_ebonhold and fr and fr != en and len(fr) >= 4 and len(en) >= 4
              and " " in en and not TOKENS.search(en)]
    paires.sort(key=lambda p: -len(p[1]))
    out = {}
    for en_desc, fr_desc in descs.items():
        trouves = []
        for en, fr in paires:
            if en in en_desc and fr in fr_desc:
                art = None
                for a in ARTICLES:
                    if (a + fr) in fr_desc:
                        art = a + fr
                        break
                trouves.append([en, fr, art])
        if trouves:
            out[en_desc] = trouves
    return out


def _codes(txt):
    # « $lsecond:seconds; » se traduit (« $lseconde:secondes; ») : seul compte sa presence.
    txt = re.sub(r"\$l[^;]*;", "$l;", txt)
    return sorted(c.rstrip(".") for c in TOKENS.findall(txt))


def verifier_codes(en, fr):
    return _codes(en) == _codes(fr)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--base", required=True)
    ap.add_argument("--plus", action="append", default=[])
    ap.add_argument("--capture", required=True)
    ap.add_argument("--sortie", required=True)
    ap.add_argument("--version", required=True)
    a = ap.parse_args()

    base = lire_json(a.base)
    names, descs = dict(base.get("names", {})), dict(base.get("descs", {}))
    refus = []
    for p in a.plus:
        if not os.path.exists(p):
            print("  (absent, ignore) %s" % p)
            continue
        x = lire_json(p)
        for cle, cible in (("names", names), ("descs", descs)):
            for en, fr in (x.get(cle) or {}).items():
                if not fr:
                    continue
                if not verifier_codes(en, fr):
                    refus.append((en, fr))
                    continue
                cible[en] = fr
        print("  + %s : %d noms, %d descriptions" % (os.path.basename(p), len(x.get("names") or {}), len(x.get("descs") or {})))
    nrem = normaliser_remplace(names, descs)
    print("  « Remplace <noeud> (Rang N). » harmonise dans %d descriptions" % nrem)
    cats, noms_ebonhold = categories_depuis_capture(a.capture)
    ndd = noms_dans_desc(names, descs, noms_ebonhold)
    out = {
        "version": a.version,
        "genere": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "categories": cats,
        "names": dict(sorted(names.items())),
        "descs": dict(sorted(descs.items())),
        "noms_dans_desc": ndd,
    }
    tmp = a.sortie + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=0)
    os.replace(tmp, a.sortie)
    print("ecrit %s : %d noms, %d descriptions, categories %s, %d descriptions citant des noms, %d refus (codes differents)"
          % (a.sortie, len(names), len(descs), {k: len(v) for k, v in cats.items()}, len(ndd), len(refus)))
    for en, fr in refus[:10]:
        print("  REFUS :", en[:80], "=>", fr[:80])


if __name__ == "__main__":
    main()
