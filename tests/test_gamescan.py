# -*- coding: utf-8 -*-
"""Tests de la recherche du jeu (gamescan) et des preferences (prefs), sans toucher au vrai PC :
faux arbre de dossiers et faux %APPDATA% dans un dossier temporaire. Seule lecture reelle :
le dossier du jeu de Dylan s'il existe (lecture seule).

    python -m unittest discover -s tests -v      (depuis le dossier launcher)
"""
import json
import os
import shutil
import struct
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TMP = tempfile.mkdtemp(prefix="ebl-scan-")
os.environ["APPDATA"] = os.path.join(_TMP, "appdata")      # AVANT d'importer core : etat isole
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "vendor"))

from core import gamescan, prefs  # noqa: E402

REAL_GAME = os.path.join(os.environ.get("LOCALAPPDATA", ""), "ebonhold")
# Variables d'environnement lues par quick_detect : videes pour ne jamais voir le vrai PC.
ENV_VIDE = {k: "" for k in ("LOCALAPPDATA", "ProgramData", "USERPROFILE", "ProgramFiles",
                            "ProgramFiles(x86)", "ProgramW6432", "PUBLIC", "OneDrive", "OneDriveConsumer")}


def touch(path, data=b""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def make_install(base, exe=True, dll=False, realm=None, config_realm=None, official=False,
                 data=True):
    if exe:
        touch(os.path.join(base, "Wow.exe"), b"MZ")
    if dll:
        touch(os.path.join(base, "ebonhold.dll"), b"MZ")
    if data:
        touch(os.path.join(base, "Data", "common.MPQ"), b"MPQ")
    if realm:
        touch(os.path.join(base, "Data", "enUS", "realmlist.wtf"), ("set realmlist %s\r\n" % realm).encode())
    if config_realm:
        touch(os.path.join(base, "WTF", "Config.wtf"),
              ('SET locale "frFR"\nSET realmList "%s"\n' % config_realm).encode())
    if official:
        touch(os.path.join(base, "Data", "patch-5.MPQ"), b"MPQ")
        touch(os.path.join(base, "verification_cache.json"), b"{}")
    return base


def make_tree():
    root = os.path.join(_TMP, "disque")
    games = os.path.join(root, "Games")
    make_install(os.path.join(games, "Ebonhold"), dll=True)
    make_install(os.path.join(games, "AutreServeur"), realm="logon.autre-serveur.com")
    make_install(os.path.join(games, "RealmSeul"), config_realm="logon.project-ebonhold.com")
    make_install(os.path.join(games, "Officiel"), official=True)
    make_install(os.path.join(games, "SansExe"), exe=False, realm="logon.project-ebonhold.com")
    make_install(os.path.join(root, "ebonhold", "Ebonhold"), dll=True)     # ancien rangement officiel
    make_install(os.path.join(root, "Profond", "a", "b", "c", "d", "e", "f", "g", "Jeu"))
    make_install(os.path.join(root, "Projet", "node_modules", "x", "Jeu"))
    make_install(os.path.join(root, "$Recycle.Bin", "Jeu"))
    touch(os.path.join(root, "Divers", "notes.txt"), b"rien")
    return root


TREE = make_tree()


def by_name(cands):
    return {os.path.basename(c["path"]): c for c in cands}


class Classement(unittest.TestCase):
    def test_marqueurs_ebonhold(self):
        g = os.path.join(TREE, "Games")
        c = gamescan.examine(os.path.join(g, "Ebonhold"))
        self.assertTrue(c["is_ebonhold"])
        self.assertIn("ebonhold.dll", c["reason"])
        self.assertTrue(c["has_exe"])
        self.assertTrue(c["label"].startswith("Ebonhold — "))

        c = gamescan.examine(os.path.join(g, "RealmSeul"))
        self.assertTrue(c["is_ebonhold"])
        self.assertIn("project-ebonhold", c["reason"])

        c = gamescan.examine(os.path.join(g, "Officiel"))
        self.assertTrue(c["is_ebonhold"])
        self.assertIn("verification_cache.json", c["reason"])

    def test_autre_serveur(self):
        c = gamescan.examine(os.path.join(TREE, "Games", "AutreServeur"))
        self.assertFalse(c["is_ebonhold"])
        self.assertIn("Autre serveur (realmlist logon.autre-serveur.com)", c["label"])

    def test_sans_exe(self):
        c = gamescan.examine(os.path.join(TREE, "Games", "SansExe"))
        self.assertTrue(c["is_ebonhold"])
        self.assertFalse(c["has_exe"])
        self.assertIn("Wow.exe absent", c["label"])

    def test_pas_un_jeu(self):
        self.assertIsNone(gamescan.examine(os.path.join(TREE, "Divers")))
        self.assertIsNone(gamescan.examine(os.path.join(TREE, "nexiste-pas")))

    def test_label_anonymise(self):
        home = os.path.join(_TMP, "Users", "Zorglub")
        game = make_install(os.path.join(home, "AppData", "Local", "ebonhold"), dll=True)
        fake = r"C:\Users\Zorglub"
        with mock.patch.dict(os.environ, {"USERNAME": "Zorglub", "USERPROFILE": fake}):
            c = gamescan.examine(game)
        self.assertNotIn("Zorglub", c["label"])
        self.assertIn("Users\\***\\AppData", c["label"])
        self.assertEqual(c["path"], os.path.abspath(game))       # le vrai chemin reste utilisable


class DetectionRapide(unittest.TestCase):
    def test_faux_arbre(self):
        with mock.patch.dict(os.environ, ENV_VIDE):
            cands = gamescan.quick_detect(drives=[TREE], use_registry=False, use_shortcuts=False)
        names = by_name(cands)
        for n in ("Ebonhold", "AutreServeur", "RealmSeul", "Officiel", "SansExe"):
            self.assertIn(n, names)
        self.assertNotIn("Jeu", names)                        # profond / node_modules / corbeille
        # Ebonhold d'abord, autres serveurs a la fin
        self.assertTrue(cands[0]["is_ebonhold"])
        self.assertFalse(cands[-1]["is_ebonhold"])
        # sous-dossier "Ebonhold" du launcher officiel (X:\ebonhold\Ebonhold)
        self.assertTrue(any(c["path"].lower().endswith(os.path.join("ebonhold", "ebonhold").lower())
                            for c in cands))

    def test_localappdata(self):
        local = os.path.join(_TMP, "local")
        make_install(os.path.join(local, "ebonhold"), dll=True)
        with mock.patch.dict(os.environ, dict(ENV_VIDE, LOCALAPPDATA=local)):
            cands = gamescan.quick_detect(drives=[], use_registry=False, use_shortcuts=False)
        self.assertEqual([os.path.normcase(c["path"]) for c in cands],
                         [os.path.normcase(os.path.join(local, "ebonhold"))])

    def test_dedoublonnage_casse(self):
        r = gamescan._Results()
        p = os.path.join(TREE, "Games", "Ebonhold")
        r.add_dir(p)
        r.add_dir(p.upper())
        r.add_dir(p + os.sep)
        self.assertEqual(len(r.items), 1)

    def test_registre(self):
        game = make_install(os.path.join(_TMP, "reg", "Ebonhold Game"), dll=True)
        other = make_install(os.path.join(_TMP, "reg", "Autre"))
        keys = {
            "{EBON}": {"DisplayName": "Ebonhold", "InstallLocation": "",
                       "UninstallString": '"%s" /S' % os.path.join(game, "uninstall.exe")},
            "Autre": {"DisplayName": "Un autre jeu", "InstallLocation": other},
        }

        class Key:
            def __init__(self, name=None):
                self.name = name

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        fake = types.SimpleNamespace(HKEY_CURRENT_USER=1, HKEY_LOCAL_MACHINE=2, KEY_READ=0)

        def open_key(parent, sub, *a):
            if isinstance(parent, Key):
                return Key(sub)
            if parent != 1:
                raise OSError("absent")
            return Key()

        def enum_key(key, i):
            names = list(keys)
            if i >= len(names):
                raise OSError("fin")
            return names[i]

        def query(key, value):
            v = keys[key.name].get(value)
            if v is None:
                raise OSError("absent")
            return v, 1

        fake.OpenKey, fake.EnumKey, fake.QueryValueEx = open_key, enum_key, query
        with mock.patch.dict(sys.modules, {"winreg": fake}):
            dirs = gamescan._registry_dirs()
        self.assertEqual([os.path.normcase(d) for d in dirs], [os.path.normcase(game)])

    def test_commande_de_desinstallation(self):
        self.assertEqual(gamescan._exe_from_command('"C:\\Jeu\\uninstall.exe" /S'), "C:\\Jeu\\uninstall.exe")
        self.assertEqual(gamescan._exe_from_command("C:\\Jeu\\ebonhold.exe,0"), "C:\\Jeu\\ebonhold.exe")
        self.assertEqual(gamescan._exe_from_command(""), "")


def make_lnk(path, target, unicode_only=False):
    """Raccourci .lnk minimal (MS-SHLLINK) : en-tete + LinkInfo avec LocalBasePath."""
    header = bytearray(0x4C)
    struct.pack_into("<I", header, 0, 0x4C)
    struct.pack_into("<I", header, 0x14, 0x02)                 # HasLinkInfo
    vol = struct.pack("<IIII", 0x10, 3, 0, 0x10)               # VolumeID minimal
    base = target.encode("mbcs" if os.name == "nt" else "latin-1") + b"\x00"
    hdr = 0x1C
    off_vol = hdr
    off_base = off_vol + len(vol)
    off_suffix = off_base + len(base)
    body = vol + base + b"\x00"
    info = struct.pack("<IIIIIII", hdr + len(body), hdr, 0x01, off_vol, off_base, 0, off_suffix) + body
    raw = bytes(header) + info
    if unicode_only:
        raw = bytes(0x4C) + b"\x00" * 8 + target.encode("utf-16-le") + b"\x00\x00"
    touch(path, raw)


class Raccourcis(unittest.TestCase):
    def test_lnk(self):
        p = os.path.join(_TMP, "lnk", "Ebonhold.lnk")
        make_lnk(p, r"D:\Jeux\Ebonhold\ebonhold.exe")
        self.assertEqual(gamescan.lnk_target(p), r"D:\Jeux\Ebonhold\ebonhold.exe")

    def test_lnk_repli_unicode(self):
        p = os.path.join(_TMP, "lnk", "WoW.lnk")
        make_lnk(p, r"E:\WoW 335\Wow.exe", unicode_only=True)
        self.assertEqual(gamescan.lnk_target(p), r"E:\WoW 335\Wow.exe")

    def test_lnk_abime(self):
        p = os.path.join(_TMP, "lnk", "abime.lnk")
        touch(p, b"pas un raccourci")
        self.assertEqual(gamescan.lnk_target(p), "")

    def test_bureau(self):
        prof = os.path.join(_TMP, "profil")
        game = make_install(os.path.join(_TMP, "via-raccourci", "Ebonhold"), dll=True)
        make_lnk(os.path.join(prof, "Desktop", "Jouer.lnk"), os.path.join(game, "Wow.exe"))
        with mock.patch.dict(os.environ, dict(ENV_VIDE, USERPROFILE=prof, APPDATA="")):
            dirs = gamescan._shortcut_dirs()
        self.assertEqual([os.path.normcase(d) for d in dirs], [os.path.normcase(game)])


class ScanComplet(unittest.TestCase):
    def test_scan(self):
        msgs = []
        cands = gamescan.scan(progress=lambda m: msgs.append((time.monotonic(), m)), stop_after=30,
                              drives=[TREE], include_quick=False)
        names = by_name(cands)
        for n in ("Ebonhold", "AutreServeur", "RealmSeul", "Officiel"):
            self.assertIn(n, names)
        self.assertNotIn("SansExe", names)        # le scan cherche Wow.exe
        self.assertNotIn("Jeu", names)            # trop profond, node_modules, $Recycle.Bin
        self.assertTrue(msgs)
        self.assertIn("Recherche terminée", msgs[-1][1])
        times = [t for t, _m in msgs[:-1]]
        self.assertTrue(all(b - a >= 0.19 for a, b in zip(times, times[1:])))   # 5 par seconde maxi

    def test_profondeur(self):
        cands = gamescan.scan(drives=[TREE], include_quick=False, max_depth=12)
        self.assertTrue(any(c["path"].endswith(os.path.join("g", "Jeu")) for c in cands))
        self.assertFalse(any("node_modules" in c["path"] for c in cands))
        self.assertFalse(any("$Recycle.Bin" in c["path"] for c in cands))

    def test_temps_imparti(self):
        t = time.monotonic()
        cands = gamescan.scan(drives=[TREE], include_quick=False, stop_after=0)
        self.assertLess(time.monotonic() - t, 2)
        self.assertEqual(cands, [])

    def test_annulation(self):
        ev = threading.Event()
        ev.set()
        self.assertEqual(gamescan.scan(drives=[TREE], include_quick=False, cancel=ev), [])

    def test_saut_des_dossiers_systeme(self):
        self.assertTrue(gamescan._skip(r"C:\Windows", "Windows"))
        self.assertTrue(gamescan._skip(r"C:\Users\x\AppData\Local\Temp", "Temp"))
        self.assertTrue(gamescan._skip(r"D:\Steam\steamapps\shadercache", "shadercache"))
        self.assertTrue(gamescan._skip(r"C:\ProgramData\Microsoft", "Microsoft"))
        self.assertTrue(gamescan._skip(r"C:\System Volume Information", "System Volume Information"))
        self.assertFalse(gamescan._skip(r"D:\Games\Ebonhold", "Ebonhold"))

    def test_disques_fixes(self):
        drives = gamescan.fixed_drives()
        self.assertIsInstance(drives, list)
        if os.name == "nt":
            self.assertTrue(all(len(d) == 3 and d.endswith(":\\") for d in drives))


@unittest.skipUnless(os.path.isdir(REAL_GAME), "jeu absent de ce PC")
class VraiJeu(unittest.TestCase):
    def test_vrai_dossier_reconnu(self):
        c = gamescan.examine(REAL_GAME)
        self.assertTrue(c["is_ebonhold"])
        self.assertTrue(c["has_exe"])
        user = os.environ.get("USERNAME", "")
        if len(user) >= 3:
            self.assertNotIn(user.lower(), c["label"].lower())


class Preferences(unittest.TestCase):
    def setUp(self):
        try:
            os.remove(prefs._file())
        except OSError:
            pass

    def test_valeurs_par_defaut(self):
        self.assertEqual(prefs.get(), {"zoom": 1.0, "first_run_done": False})

    def test_zoom(self):
        self.assertTrue(prefs.set("zoom", 1.25)["ok"])
        self.assertEqual(prefs.get()["zoom"], 1.25)
        self.assertTrue(prefs.set("zoom", "1.6")["ok"])
        for bad in (0.5, 1.7, "abc", True, None, float("nan")):
            r = prefs.set("zoom", bad)
            self.assertFalse(r["ok"], bad)
            self.assertTrue(r["error"])
        self.assertEqual(prefs.get()["zoom"], 1.6)

    def test_premier_lancement(self):
        self.assertTrue(prefs.set("first_run_done", True)["ok"])
        self.assertTrue(prefs.get()["first_run_done"])
        self.assertFalse(prefs.set("first_run_done", "oui")["ok"])
        self.assertFalse(prefs.set("inconnu", 1)["ok"])
        with open(prefs._file(), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["first_run_done"], True)

    def test_fichier_abime_garde_de_cote(self):
        with open(prefs._file(), "w") as f:
            f.write("{pas du json")
        self.assertEqual(prefs.get()["zoom"], 1.0)
        d = os.path.dirname(prefs._file())
        self.assertTrue(any(n.startswith("prefs.json.abime-") for n in os.listdir(d)))

    def test_valeur_invalide_dans_le_fichier(self):
        with open(prefs._file(), "w") as f:
            json.dump({"zoom": 9, "first_run_done": "x", "autre": 1}, f)
        self.assertEqual(prefs.get(), {"zoom": 1.0, "first_run_done": False})

    def test_ecritures_simultanees(self):
        errs = []

        def w(i):
            try:
                prefs.set("zoom", 0.8 + (i % 9) * 0.1)
            except Exception as e:      # noqa: BLE001
                errs.append(e)
        ts = [threading.Thread(target=w, args=(i,)) for i in range(20)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(errs, [])
        self.assertTrue(0.8 <= prefs.get()["zoom"] <= 1.6)


def tearDownModule():
    shutil.rmtree(_TMP, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
