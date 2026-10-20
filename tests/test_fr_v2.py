# -*- coding: utf-8 -*-
"""Tests du constructeur de patch FR v2 (vendor/fr_patch.py) sur des DBC synthetiques."""
import os
import struct
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("APPDATA", tempfile.mkdtemp(prefix="ebl-frv2-"))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "vendor"))

import fr_patch as P  # noqa: E402


def make_dbc(fc, rows, strings_fields):
    """rows = [(id, {champ: texte})] ; strings_fields = champs texte. Renvoie les octets WDBC."""
    pool = bytearray(b"\x00")
    offs = {}

    def add(s):
        b = s.encode("utf-8")
        if b not in offs:
            offs[b] = len(pool)
            pool.extend(b + b"\x00")
        return offs[b]
    recs = bytearray()
    for rid, vals in rows:
        rec = [0] * fc
        rec[0] = rid
        for f, t in vals.items():
            rec[f] = add(t)
        recs.extend(struct.pack("<%dI" % fc, *rec))
    return struct.pack("<4sIIII", b"WDBC", len(rows), fc, fc * 4, len(pool)) + bytes(recs) + bytes(pool)


def read(buf, rid, field):
    _, n, fc, rs, _ = struct.unpack("<4sIIII", buf[:20])
    base = 20 + n * rs
    for i in range(n):
        rec = struct.unpack_from("<%dI" % fc, buf, 20 + i * rs)
        if rec[0] == rid:
            o = rec[field]
            return buf[base + o:buf.index(b"\x00", base + o)].decode("utf-8") if o else ""


DATA = {"version": "t", "names": {"Exposed Heart": "Cœur exposé", "Death Grip": "Étreinte de la Mort"},
        "descs": {"Increases damage by $s1%.": "Augmente les dégâts de $s1 %.",
                  "Grants Exposed Heart.": "Accorde Cœur exposé."},
        "categories": {"echo": {200001}, "soultree": set(), "affix": set(), "tome": set()},
        "noms_dans_desc": {"Grants Exposed Heart.": [["Exposed Heart", "Cœur exposé", None]]}}
FC = 234
SPELL = make_dbc(FC, [
    (49576, {136: "Death Grip", 170: "Pulls the target."}),
    (200001, {136: "Exposed Heart", 170: "Increases damage by $s1%."}),
    (1000001, {136: "Exposed Heart", 170: "Grants Exposed Heart."}),
], ())
BASE = make_dbc(FC, [(49576, {138: "Poigne de la mort", 172: "Attire la cible."})], ())


class SpellDbc(unittest.TestCase):
    def test_recommande(self):
        out = P.construire_spell(SPELL, BASE, DATA, P.normaliser(P.PRESETS["recommande"]))
        self.assertEqual(read(out, 49576, 138), "Poigne de la mort")       # nom officiel, jamais la trad maison
        self.assertEqual(read(out, 49576, 136), "Poigne de la mort")       # aussi en colonne enUS
        self.assertEqual(read(out, 200001, 138), "Exposed Heart")          # noms Ebonhold en anglais
        self.assertEqual(read(out, 200001, 172), "Augmente les dégâts de $s1 %.")
        self.assertEqual(read(out, 1000001, 172), "Accorde Exposed Heart.")  # nom remis en anglais

    def test_tout_fr(self):
        out = P.construire_spell(SPELL, BASE, DATA, P.normaliser(P.PRESETS["tout_fr"]))
        self.assertEqual(read(out, 200001, 138), "Cœur exposé")
        self.assertEqual(read(out, 1000001, 172), "Accorde Cœur exposé.")
        self.assertEqual(read(out, 49576, 138), "Poigne de la mort")

    def test_tout_en(self):
        out = P.construire_spell(SPELL, BASE, DATA, P.normaliser(P.PRESETS["tout_en"]))
        for rid, f, t in ((49576, 138, "Death Grip"), (200001, 172, "Increases damage by $s1%."),
                          (1000001, 138, "Exposed Heart")):
            self.assertEqual(read(out, rid, f), t)

    def test_sans_pack(self):
        out = P.construire_spell(SPELL, None, DATA, P.normaliser(P.PRESETS["tout_fr"]))
        self.assertEqual(read(out, 49576, 138), "Death Grip")              # pas de FR officiel : anglais


class AutresDbc(unittest.TestCase):
    def test_chaine_non_traduite_intacte(self):
        # champ 1 = chemin (non traduit), bloc localise en 2..18 (enUS=2, frFR=4)
        raw = make_dbc(20, [(1, {1: "Interface\\Icons\\Foo", 2: "Increases damage by $s1%."})], ())
        raw = raw.replace(b"", b"")
        out = P.construire_dbc("SpellItemEnchantment.dbc", raw, None, DATA, P.normaliser({}))
        self.assertIsNotNone(out)
        self.assertEqual(read(out, 1, 1), "Interface\\Icons\\Foo")
        self.assertEqual(read(out, 1, 4), "Augmente les dégâts de $s1 %.")

    def test_reglage_en(self):
        raw = make_dbc(20, [(1, {2: "Increases damage by $s1%."})], ())
        out = P.construire_dbc("SpellItemEnchantment.dbc", raw, None, DATA, P.normaliser({"affixes_desc": "en"}))
        self.assertEqual(read(out, 1, 4), "Increases damage by $s1%.")

    def test_fichier_sans_reglage(self):
        raw = make_dbc(20, [(1, {2: "x"})], ())
        self.assertIsNone(P.construire_dbc("CreatureDisplayInfo.dbc", raw, None, DATA, P.normaliser({})))


class Reglages(unittest.TestCase):
    def test_normaliser(self):
        s = P.normaliser({"jeu": "en", "inconnu": "fr", "tomes": "peut-etre", "nom_anglais": 0})
        self.assertEqual(s["jeu"], "en")
        self.assertNotIn("inconnu", s)
        self.assertEqual(s["tomes"], "fr")
        self.assertFalse(s["nom_anglais"])

    def test_preselections(self):
        self.assertTrue(all(v == "fr" for k, v in P.PRESETS["tout_fr"].items() if k in P.CLES_FR_EN))
        self.assertEqual(P.PRESETS["recommande"]["echoes_noms"], "en")
        self.assertEqual(P.PRESETS["recommande"]["echoes_desc"], "fr")


if __name__ == "__main__":
    unittest.main(verbosity=2)
