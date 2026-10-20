"""Constructeur des DBC traduits du patch FR (patch-Z), partie par partie (launcher v2).

Chaque ligne de chaque DBC est traitee selon les reglages FR / EN du joueur :
  - Spell.dbc : categorie du sort (echo, soultree, affix, tome, blizzard, autre sort Ebonhold),
    puis colonne (nom, rang, description, infobulle d'aura) ;
  - les autres DBC : tout le fichier suit un seul reglage (reputations, hauts faits, metiers…).

Source du texte francais, dans l'ordre :
  1. notre base (cle = texte anglais exact du serveur) : `names` pour les noms, `descs` sinon ;
  2. le francais officiel Blizzard du pack frFR (meme ID), pour ce qui vient de Blizzard ;
  3. sinon l'anglais.
Pour un sort Blizzard, le NOM est toujours le nom francais officiel (jamais une traduction
maison), et la description maison n'est prise que si le serveur a change le texte.

Le texte choisi est ecrit dans les colonnes enUS ET frFR : il s'affiche quelle que soit la
langue reelle du client. Le bloc de chaines d'ORIGINE est conserve tel quel et les nouvelles
chaines sont ajoutees a la suite : les champs texte non traduits (chemins, noms internes)
gardent leurs offsets valides.
"""
import json
import re
import struct

# --------------------------------------------------------------------------- reglages
DEFAUTS = {
    "jeu": "fr", "voix": "fr", "sorts_blizzard": "fr", "reputations": "fr", "hauts_faits": "fr",
    "metiers": "fr", "echoes_desc": "fr", "echoes_noms": "en", "soultree_desc": "fr",
    "soultree_noms": "en", "affixes_desc": "fr", "affixes_noms": "en", "tomes": "fr",
    "interface": "fr", "nom_anglais": True,
}
CLES_FR_EN = [k for k, v in DEFAUTS.items() if v in ("fr", "en")]
PRESETS = {
    "recommande": dict(DEFAUTS),
    "tout_fr": dict({k: "fr" for k in CLES_FR_EN}, nom_anglais=True),
    "tout_en": dict({k: "en" for k in CLES_FR_EN}, nom_anglais=False),
}
BESOIN_PACK = ("jeu", "voix", "sorts_blizzard")   # sans le pack : pas de francais officiel


def normaliser(settings):
    """Reglages complets et valides (cles inconnues ignorees, valeurs par defaut sinon)."""
    out = dict(DEFAUTS)
    for k, v in (settings or {}).items():
        if k in CLES_FR_EN and v in ("fr", "en"):
            out[k] = v
        elif k == "nom_anglais":
            out[k] = bool(v)
    return out


def fr(settings, cle):
    return settings.get(cle) == "fr"


# Quel reglage pilote chaque DBC (hors Spell.dbc). None = jamais traduit par le patch.
DBC_REGLAGE = {
    "faction.dbc": "reputations",
    "achievement.dbc": "hauts_faits", "achievement_category.dbc": "hauts_faits",
    "achievement_criteria.dbc": "hauts_faits", "chartitles.dbc": "hauts_faits",
    "skillline.dbc": "metiers", "skilllinecategory.dbc": "metiers",
    "spellitemenchantment.dbc": "affixes_desc", "itemrandomproperties.dbc": "affixes_noms",
    "questinfo.dbc": "jeu", "questsort.dbc": "jeu",
    "spellrange.dbc": "sorts_blizzard",
}
# Dans ces DBC, la colonne texte est un nom (dictionnaire `names`), pas une description.
DBC_NOMS = {"itemrandomproperties.dbc"}

# Colonnes enUS de Spell.dbc (3.3.5a) ; frFR = enUS + 2.
SPELL_NOM, SPELL_RANG, SPELL_DESC, SPELL_AURA = 136, 153, 170, 187


# --------------------------------------------------------------------------- donnees
def charger_donnees(*chemins):
    """Fusionne des fichiers de traduction ({names, descs, categories, version}) : les suivants
    completent et remplacent les precedents. Fichiers absents ou illisibles ignores."""
    d = {"version": "0", "names": {}, "descs": {}, "categories": {}, "noms_dans_desc": {}}
    for p in chemins:
        if not p:
            continue
        try:
            with open(p, encoding="utf-8") as f:
                x = json.load(f)
        except (OSError, ValueError):
            continue
        d["names"].update(x.get("names") or {})
        d["descs"].update(x.get("descs") or {})
        d["noms_dans_desc"].update(x.get("noms_dans_desc") or {})
        for cat, ids in (x.get("categories") or {}).items():
            d["categories"].setdefault(cat, set()).update(int(i) for i in ids)
        if x.get("version"):
            d["version"] = str(x["version"])
    for cat in d["categories"]:
        d["categories"][cat] = set(d["categories"][cat])
    return d


def categorie_sort(sid, data, ids_blizzard):
    cats = data["categories"]
    for cat in ("echo", "soultree", "affix", "tome"):
        if sid in cats.get(cat, ()):
            return cat
    if ids_blizzard is not None:
        return "blizzard" if sid in ids_blizzard else "ebonhold"
    return "blizzard" if sid < 90000 else "ebonhold"


# Reglages (nom, description) de chaque categorie de sort.
REGLAGE_SORT = {
    "echo": ("echoes_noms", "echoes_desc"),
    "ebonhold": ("echoes_noms", "echoes_desc"),     # autres sorts propres au serveur (effets, procs)
    "soultree": ("soultree_noms", "soultree_desc"),
    "affix": ("affixes_noms", "affixes_desc"),
    "tome": ("echoes_noms", "tomes"),     # « Tome of <echo> » : le nom suit celui des echoes
    "blizzard": ("sorts_blizzard", "sorts_blizzard"),
}

_RANG = re.compile(r"^Rank (\d+)$")


def remettre_noms_anglais(fr_txt, en_txt, data):
    """Noms en anglais demandes : les noms Ebonhold traduits a l'interieur d'une description
    francaise redeviennent anglais (« découvrir le Miroir de Sang » -> « découvrir Blood Mirror »).
    Les paires (anglais, francais) de chaque description sont calculees a l'avance par le
    generateur de donnees (`noms_dans_desc`), du plus long au plus court."""
    for en_nom, fr_nom, avec_article in data["noms_dans_desc"].get(en_txt, ()):
        if avec_article:
            fr_txt = fr_txt.replace(avec_article, en_nom)
        fr_txt = fr_txt.replace(fr_nom, en_nom)
    return fr_txt


# --------------------------------------------------------------------------- format WDBC
def _lire(buf):
    magic, rc, fc, rs, sbs = struct.unpack("<4sIIII", buf[:20])
    if magic != b"WDBC":
        raise ValueError("pas un fichier WDBC")
    if rs != fc * 4:
        raise ValueError("enregistrements non alignes sur 4 octets")
    return rc, fc, rs, sbs, buf[20 + rc * rs: 20 + rc * rs + sbs]


def _chaine(bloc, off):
    if off <= 0 or off >= len(bloc):
        return b""
    return bloc[off:bloc.find(b"\x00", off)]


class _Pool:
    """Bloc de chaines : l'original intact, les nouvelles chaines ajoutees a la fin."""

    def __init__(self, original):
        self.data = bytearray(original if original else b"\x00")
        if not self.data.endswith(b"\x00"):
            self.data.append(0)
        self.index = {}

    def add(self, s):
        if not s:
            return 0
        if s in self.index:
            return self.index[s]
        o = len(self.data)
        self.data.extend(s)
        self.data.append(0)
        self.index[s] = o
        return o


def _blocs_localises(buf):
    """Champs de debut des blocs de chaines localisees (16 locales + 1 drapeau)."""
    import dbc_localize           # detection existante, eprouvee
    blocks, _ = dbc_localize.detect_blocks(buf)
    return blocks


def _carte_base(base, blocs):
    """{id: {bloc: texte FR officiel}} depuis le DBC du pack frFR."""
    if not base:
        return {}
    rc, fc, rs, sbs, bloc = _lire(base)
    out = {}
    for i in range(rc):
        o = 20 + i * rs
        rec = struct.unpack_from("<%dI" % fc, base, o)
        out[rec[0]] = {b0: _chaine(bloc, rec[b0 + 2]) for b0 in blocs if b0 + 2 < fc}
    return out


def _ecrire(raw, rc, fc, rs, recs, pool):
    out = bytearray(struct.pack("<4sIIII", b"WDBC", rc, fc, rs, len(pool.data)))
    for rec in recs:
        out.extend(struct.pack("<%dI" % fc, *rec))
    out.extend(pool.data)
    return bytes(out)


def _poser(rec, b0, valeur, pool):
    """Le texte choisi dans enUS (b0) et frFR (b0+2), les autres locales videes."""
    o = pool.add(valeur)
    for k in range(16):
        rec[b0 + k] = 0
    rec[b0] = o
    rec[b0 + 2] = o


# --------------------------------------------------------------------------- Spell.dbc
def construire_spell(raw, base, data, settings, stats=None):
    """Spell.dbc traduit selon les reglages. `base` = Spell.dbc du pack frFR (ou None)."""
    stats = stats if stats is not None else {}
    rc, fc, rs, sbs, bloc = _lire(raw)
    blocs = [b for b in (SPELL_NOM, SPELL_RANG, SPELL_DESC, SPELL_AURA) if b + 16 < fc]
    carte = _carte_base(base, blocs)
    ids_blizzard = set(carte) if carte else None
    names, descs = data["names"], data["descs"]
    pool = _Pool(bloc)
    recs = []
    for i in range(rc):
        rec = list(struct.unpack_from("<%dI" % fc, raw, 20 + i * rs))
        sid = rec[0]
        cat = categorie_sort(sid, data, ids_blizzard)
        cle_nom, cle_desc = REGLAGE_SORT[cat]
        nom_fr, desc_fr = fr(settings, cle_nom), fr(settings, cle_desc)
        off = carte.get(sid, {})
        for b0 in blocs:
            en = _chaine(bloc, rec[b0])
            choix = en
            if en:
                t = en.decode("utf-8", "replace")
                if b0 == SPELL_NOM:
                    if nom_fr:
                        if cat == "blizzard":
                            choix = off.get(b0) or en
                        elif t in names:
                            choix = names[t].encode("utf-8")
                elif b0 == SPELL_RANG:      # « Rank 1 », « Passive », « Racial »… : suit la description
                    if desc_fr:
                        if off.get(b0):
                            choix = off[b0]
                        elif t in descs:
                            choix = descs[t].encode("utf-8")
                        else:
                            m = _RANG.match(t)
                            if m:
                                choix = ("Rang %s" % m.group(1)).encode("utf-8")
                else:   # description, infobulle d'aura
                    if desc_fr:
                        if t in descs:
                            txt = descs[t]
                            if not nom_fr and cat != "blizzard":
                                txt = remettre_noms_anglais(txt, t, data)
                            choix = txt.encode("utf-8")
                        elif cat == "blizzard" and off.get(b0):
                            choix = off[b0]
            if choix != en:
                stats["traduits"] = stats.get("traduits", 0) + 1
            _poser(rec, b0, choix, pool)
        recs.append(rec)
    stats["lignes"] = rc
    return _ecrire(raw, rc, fc, rs, recs, pool)


# --------------------------------------------------------------------------- autres DBC
def construire_dbc(nom_fichier, raw, base, data, settings, stats=None):
    """DBC hors Spell.dbc traduit (ou remis en anglais) selon le reglage qui le pilote.
    Renvoie None si ce fichier n'a pas de texte a traiter."""
    stats = stats if stats is not None else {}
    cle = DBC_REGLAGE.get(nom_fichier.lower())
    if cle is None:
        return None
    rc, fc, rs, sbs, bloc = _lire(raw)
    blocs = _blocs_localises(raw)
    if not blocs:
        return None
    actif = fr(settings, cle)
    dico = data["names"] if nom_fichier.lower() in DBC_NOMS else data["descs"]
    autre = data["descs"] if dico is data["names"] else data["names"]
    carte = _carte_base(base, blocs) if actif else {}
    pool = _Pool(bloc)
    recs = []
    for i in range(rc):
        rec = list(struct.unpack_from("<%dI" % fc, raw, 20 + i * rs))
        off = carte.get(rec[0], {})
        for b0 in blocs:
            en = _chaine(bloc, rec[b0])
            choix = en
            if en and actif:
                t = en.decode("utf-8", "replace")
                if t in dico:
                    choix = dico[t].encode("utf-8")
                elif off.get(b0):
                    choix = off[b0]
                elif t in autre:
                    choix = autre[t].encode("utf-8")
            if choix != en:
                stats["traduits"] = stats.get("traduits", 0) + 1
            _poser(rec, b0, choix, pool)
        recs.append(rec)
    stats["lignes"] = rc
    return _ecrire(raw, rc, fc, rs, recs, pool)
