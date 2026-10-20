# -*- coding: utf-8 -*-
"""Tests du launcher, sans reseau ni vrai jeu : un faux dossier WoW et un faux %APPDATA%
sont crees dans un dossier temporaire.

    python -m unittest discover -s tests -v      (depuis le dossier launcher)
"""
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TMP = tempfile.mkdtemp(prefix="ebl-tests-")
os.environ["APPDATA"] = os.path.join(_TMP, "appdata")      # AVANT d'importer core : etat isole
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "vendor"))

from core import api, catalog, frconfig, frpack, installer, selfupdate, state, version  # noqa: E402


def make_game(name):
    g = os.path.join(_TMP, name)
    os.makedirs(os.path.join(g, "Data"), exist_ok=True)
    os.makedirs(os.path.join(g, "Interface", "AddOns"), exist_ok=True)
    open(os.path.join(g, "Data", "patch-5.MPQ"), "wb").close()
    return g


def make_zip(path, entries):
    with zipfile.ZipFile(path, "w") as z:
        for n, data in entries.items():
            z.writestr(n, data)
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


class Versions(unittest.TestCase):
    def test_suffixe_fr(self):
        self.assertTrue(version.is_newer("1.1.7", "1.1.6-fr1"))     # ancienne lecture : 1.1.61
        self.assertTrue(version.is_newer("1.2.0", "1.1.6-fr1"))
        self.assertTrue(version.is_newer("1.1.6-fr2", "1.1.6-fr1"))
        self.assertFalse(version.is_newer("1.1.6", "1.1.6-fr1"))

    def test_egalites(self):
        self.assertEqual(version.normalize("2.76"), version.normalize("2.76.0"))
        self.assertEqual(version.normalize("v.1.25"), version.normalize("1.25"))
        self.assertEqual(version.normalize("v3.1"), "3.1")
        self.assertFalse(version.is_newer("1.0.10", "1.0.10"))
        self.assertTrue(version.is_newer("1.0.11", "1.0.10"))
        self.assertTrue(version.is_newer("1.0.10", "1.0.9"))


class Etat(unittest.TestCase):
    def test_ecritures_simultanees(self):
        errs = []

        def w(i):
            try:
                state.mark_installed("p%d" % i, "1.%d" % i, ["Interface/AddOns/P%d" % i])
            except Exception as e:      # noqa: BLE001
                errs.append(e)
        ts = [threading.Thread(target=w, args=(i,)) for i in range(30)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(errs, [])
        inst = state.load()["installed"]
        self.assertTrue(all("p%d" % i in inst for i in range(30)))

    def test_fichier_abime_garde_de_cote(self):
        with open(state._STATE_FILE, "w") as f:
            f.write("{pas du json")
        self.assertEqual(state.load()["installed"], {})
        d = os.path.dirname(state._STATE_FILE)
        self.assertTrue(any(n.startswith("state.json.abime-") for n in os.listdir(d)))


class Catalogue(unittest.TestCase):
    def test_cache_prefere_sauf_si_plus_ancien(self):
        local = catalog._load_local()
        cache = dict(local, products=[{"id": "x"}], launcher_version=local.get("launcher_version", "1.0.0"))
        catalog._save_cache(cache)
        man, src = catalog.fetch_offline()
        self.assertEqual(src, "cache")
        catalog._save_cache(dict(cache, launcher_version="0.0.1"))
        man, src = catalog.fetch_offline()
        self.assertEqual(src, "local")

    def test_rechargement_garde_le_catalogue_en_ligne(self):
        a = api.Api()
        # Pas de taches de fond : elles chercheraient le vrai jeu et ecriraient l'etat
        # pendant les autres tests.
        a._startup_done, a._detect_wow = True, lambda: None
        a._manifest, a._source = {"products": [], "launcher_version": "9.9.9"}, "remote"
        r = a.get_catalog(False)
        self.assertEqual(r["source"], "remote")      # avant : retour au catalogue embarque


class ApiV2(unittest.TestCase):
    def test_dossier_du_jeu(self):
        a = api.Api()
        self.assertFalse(a.set_wow_path(os.path.join(_TMP, "pas-un-jeu"))["ok"])
        g = make_game("jeu-api")
        self.assertTrue(a.set_wow_path(g)["ok"])
        self.assertEqual(state.get_wow_path(), g)

    def test_preferences(self):
        a = api.Api()
        self.assertTrue(a.set_pref("zoom", 1.25)["ok"])
        self.assertEqual(a.get_prefs()["zoom"], 1.25)
        self.assertFalse(a.set_pref("inconnue", 1)["ok"])

    def test_signalement_verifie_avant_envoi(self):
        a = api.Api()
        r = a.send_report("bug", "court", [], True)
        self.assertFalse(r["started"])
        self.assertIn("10 caractères", r["error"])


class Liens(unittest.TestCase):
    def test_liens(self):
        self.assertTrue(api._url_ok("https://github.com/Squall98/EbonholdFR/releases"))
        self.assertTrue(api._url_ok("https://discord.gg/abc"))
        self.assertTrue(api._url_ok("https://squall98.github.io/ebonhold-skilltree/"))
        for bad in ("http://github.com/x", "file:///C:/Windows/System32/calc.exe",
                    "C:\\Windows\\System32\\calc.exe", "https://evil.example/github.com",
                    "https://github.com.evil.example/", "javascript:alert(1)"):
            self.assertFalse(api._url_ok(bad), bad)


class Installation(unittest.TestCase):
    def setUp(self):
        self.game = make_game("jeu-%s" % self._testMethodName)
        state.set_wow_path(self.game)

    def product(self, entries, root="MonAddon", pid="monaddon", ver="1.0"):
        z = os.path.join(_TMP, pid + "-" + self._testMethodName + ".zip")
        sha = make_zip(z, entries)
        return {"id": pid, "name": "Mon addon", "category": "interface", "version": ver, "install_target": "addons",
                "extract_root": root, "download_url": z, "sha256": sha}

    def test_seuls_les_dossiers_declares(self):
        p = self.product({"MonAddon/MonAddon.toc": "## Version: 1.0", "AutreAddon/x.lua": "--",
                          "ProjectEbonhold/piege.lua": "--"})
        installer.install(p, self.game)
        ad = os.path.join(self.game, "Interface", "AddOns")
        self.assertTrue(os.path.isfile(os.path.join(ad, "MonAddon", "MonAddon.toc")))
        self.assertFalse(os.path.exists(os.path.join(ad, "AutreAddon")))
        self.assertFalse(os.path.exists(os.path.join(ad, "ProjectEbonhold")))

    def test_dossier_reserve_refuse(self):
        p = self.product({"ProjectEbonhold/a.lua": "--"}, root="ProjectEbonhold", pid="piege")
        with self.assertRaises(ValueError):
            installer.install(p, self.game)

    def test_dossier_absent_du_zip(self):
        p = self.product({"Autre/a.lua": "--"}, root="MonAddon", pid="faux")
        with self.assertRaises(ValueError):
            installer.install(p, self.game)

    def test_zip_slip(self):
        z = zipfile.ZipFile(io.BytesIO(), "w")
        z.writestr("MonAddon/../../evil.txt", "x")
        with self.assertRaises(ValueError):
            installer._safe_extract(z, os.path.join(self.game, "Interface", "AddOns"), ["MonAddon"])

    def test_tout_mettre_a_jour_ne_touche_que_l_installe(self):
        a = api.Api()
        old = self.product({"MonAddon/MonAddon.toc": "## Version: 1.0"}, ver="1.0")
        installer.install(old, self.game)
        new = dict(old, version="1.1")
        other = self.product({"Autre/Autre.toc": "## Version: 1.0"}, root="Autre", pid="autre")
        a._manifest, a._source = {"products": [new, other], "launcher_version": "0"}, "remote"
        rows = {r["id"]: r for r in a._build_catalog()["products"]}
        self.assertEqual(rows["monaddon"]["status"], "update")
        self.assertEqual(rows["autre"]["status"], "install")
        self.assertEqual(a._build_catalog()["updates_count"], 1)
        r = a.install_all()
        self.assertEqual(r["ids"], ["monaddon"])
        a._worker.join(10)
        self.assertEqual(state.get_installed("monaddon")["version"], "1.1")
        self.assertIsNone(state.get_installed("autre"))


class PatchFR(unittest.TestCase):
    def test_priorite_des_patchs(self):
        d = os.path.join(_TMP, "prio")
        os.makedirs(d, exist_ok=True)
        for n in ("patch.MPQ", "patch-2.MPQ", "patch-4.MPQ", "patch-5.MPQ", "patch-D.mpq",
                  "patch-M.MPQ", "patch-X.MPQ", "patch-Z.MPQ", "common.MPQ"):
            open(os.path.join(d, n), "wb").close()
        self.assertEqual(frconfig._patches_by_priority(d),
                         ["patch-X.MPQ", "patch-M.MPQ", "patch-D.mpq", "patch-5.MPQ",
                          "patch-4.MPQ", "patch-2.MPQ", "patch.MPQ"])

    def test_extraction_directe_du_pack(self):
        data = os.path.join(make_game("jeu-pack"), "Data")
        z = os.path.join(_TMP, "pack.zip")
        make_zip(z, {"frFR/locale-frFR.MPQ": b"x" * 100, "frFR/realmlist.wtf": "set realmlist x",
                     "frFR/../../evil.txt": "x", "Lisez-moi.txt": "hors frFR"})
        self.assertTrue(frpack._extract_frfr_zip(z, data))
        self.assertTrue(frconfig.has_pack(data))
        self.assertFalse(os.path.exists(os.path.join(_TMP, "evil.txt")))
        self.assertFalse(any(n.endswith(".partiel") for n in os.listdir(os.path.join(data, "frFR"))))

    def test_reprise_apres_coupure(self):
        payload = bytes(range(256)) * 4000
        calls = []

        class Resp:
            def __init__(self, data, status, cut=None):
                self.data, self.status, self.cut, self.pos = data, status, cut, 0
                self.headers = {"Content-Length": str(len(data))}

            def read(self, n):
                if self.cut is not None and self.pos >= self.cut:
                    raise ConnectionResetError("coupure")
                chunk = self.data[self.pos:self.pos + min(n, 50000)]
                self.pos += len(chunk)
                return chunk

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake_urlopen(req, timeout=0):
            rng = req.headers.get("Range")
            calls.append(rng)
            if rng:
                start = int(rng.split("=")[1].rstrip("-"))
                return Resp(payload[start:], 206)
            return Resp(payload, 200, cut=300000)

        import urllib.request
        real, frpack.time.sleep = urllib.request.urlopen, lambda s: None
        urllib.request.urlopen = fake_urlopen
        try:
            buf = io.BytesIO()
            frpack._append_url("https://example/x", buf)
        finally:
            urllib.request.urlopen = real
        self.assertEqual(buf.getvalue(), payload)
        self.assertIsNone(calls[0])
        self.assertTrue(calls[1].startswith("bytes="))

    def test_traductions_ajoutees(self):
        tr = frconfig._load_tr()
        self.assertIn("You can now ride flying mounts in Northrend.", tr)
        self.assertTrue(any(k.startswith("Your direct-damage abilities apply an Unstable Infusion") for k in tr))


class AutoMiseAJour(unittest.TestCase):
    def test_pas_de_miroir_a_la_racine(self):
        new = os.path.join(_TMP, "upd", "EbonholdLauncher")
        os.makedirs(os.path.join(new, "_internal"), exist_ok=True)
        s = selfupdate.swapper_script(r"C:\Users\Joueur\Desktop", new, "EbonholdLauncher.exe", r"C:\Temp\x")
        mir = [l for l in s.splitlines() if "/MIR" in l]
        self.assertEqual(len(mir), 1)
        self.assertIn("_internal", mir[0])
        self.assertIn('robocopy "%s" "C:\\Users\\Joueur\\Desktop" /R:3' % new, s)

    def test_sha_obligatoire(self):
        selfupdate.is_frozen = lambda: True
        try:
            with self.assertRaises(ValueError):
                selfupdate.download_and_swap("https://github.com/x.zip", "")
        finally:
            selfupdate.is_frozen = lambda: bool(getattr(sys, "frozen", False))


def tearDownModule():
    shutil.rmtree(_TMP, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
