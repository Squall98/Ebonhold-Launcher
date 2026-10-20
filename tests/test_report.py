# -*- coding: utf-8 -*-
"""Tests de "Signaler un bug" (report), des infos du jeu (gameinfo) et de l'anonymisation,
SANS reseau : un faux transport HTTP joue le role de GitHub, un faux dossier de jeu et un faux
%APPDATA% sont crees dans un dossier temporaire. Le vrai dossier du jeu de Dylan est lu (lecture
seule) s'il existe, pour verifier qu'aucun nom d'utilisateur ne sort.

    python -m unittest discover -s tests -v      (depuis le dossier launcher)
"""
import base64
import json
import os
import re
import shutil
import sys
import tempfile
import time
import unittest
import urllib.parse
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TMP = tempfile.mkdtemp(prefix="ebl-report-")
os.environ["APPDATA"] = os.path.join(_TMP, "appdata")      # AVANT d'importer core : etat isole
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "vendor"))

from core import anonymize, gameinfo, paths, report  # noqa: E402

TOKEN = "github_pat_11FAUXJETON_pour_les_tests_0123456789abcdef"
REPO = "Squall98/Ebonhold-Signalements-Test"
REAL_GAME = os.path.join(os.environ.get("LOCALAPPDATA", ""), "ebonhold")
FAKE_ENV = {"USERNAME": "Zorglub", "COMPUTERNAME": "PC-ZORGLUB", "USERPROFILE": r"C:\Users\Zorglub",
            "USERDOMAIN": "PC-ZORGLUB"}

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64


def touch(path, data=b""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    return path


def make_game():
    g = os.path.join(_TMP, "jeu")
    touch(os.path.join(g, "Wow.exe"), b"MZ")
    touch(os.path.join(g, "ebonhold.dll"), b"MZ" * 100)
    touch(os.path.join(g, "ClientExt.dll"), b"MZ")
    touch(os.path.join(g, "Data", "common.MPQ"), b"MPQ" * 10)
    touch(os.path.join(g, "Data", "patch-5.MPQ"), b"patch5")
    touch(os.path.join(g, "Data", "frFR", "patch-frFR-4.MPQ"), b"fr")
    touch(os.path.join(g, "Data", "frFR", "realmlist.wtf"), b"set realmlist logon.project-ebonhold.com\r\n")
    touch(os.path.join(g, "WTF", "Config.wtf"), (
        'SET locale "frFR"\r\nSET accountName "COMPTESECRET"\r\nSET accountList "COMPTESECRET|AUTRECOMPTE|"\r\n'
        'SET lastCharacterIndex "3"\r\nSET realmList "logon.project-ebonhold.com"\r\nSET gxWindow "1"\r\n'
        'SET gxResolution "1920x1080"\r\nSET gxApi "d3d9"\r\nSET accounttype "LK"\r\n').encode())
    touch(os.path.join(g, "WTF", "Account", "COMPTESECRET", "SavedVariables", "x.lua"), b"")
    touch(os.path.join(g, "Interface", "AddOns", "MonAddon", "MonAddon.toc"),
          b"## Interface: 30300\n## Title: |cff00ff00Mon|r Addon\n## Version: 1.2.3\n")
    touch(os.path.join(g, "Interface", "AddOns", "SansToc", "x.lua"), b"")
    os.makedirs(os.path.join(g, "Interface", "AddOns", "Blizzard_AuctionUI"), exist_ok=True)
    touch(os.path.join(g, "ebonhold.log"), "\n".join(
        ["[init] ligne %d" % i for i in range(200)] +
        [r"[clientext] loaded C:\Users\Zorglub\AppData\Local\Ebonhold\ClientExt.dll",
         "[login] compte COMPTESECRET connecte depuis PC-ZORGLUB", "[mail] zorglub@exemple.fr"]).encode())
    touch(os.path.join(g, "Logs", "FrameXML.log"), b"\n".join(b"frame %d" % i for i in range(100)))
    touch(os.path.join(g, "Logs", "GlueXML.log"), b"glue ok")
    touch(os.path.join(g, "Logs", "connection.log"), b"NE PAS JOINDRE")
    touch(os.path.join(g, "Errors", "2026-10-19 crash.txt"), b"old")
    time.sleep(0.01)
    touch(os.path.join(g, "Errors", "2026-10-20 crash.txt"), (
        "World of WarCraft (build 12340)\r\nExe: C:\\Users\\Zorglub\\Jeu\\Wow.exe\r\nUser: Zorglub\r\n"
        "Computer: PC-ZORGLUB\r\nThis application has encountered a critical error:\r\n"
        "ERROR #132 (0x85100084) Fatal Exception\r\nProcessor: Intel quelque chose\r\n").encode())
    return g


GAME = make_game()


def write_config(cfg):
    p = os.path.join(_TMP, "secrets", "report.json")
    touch(p, json.dumps(cfg).encode())
    report._CONFIG_OVERRIDE = p
    return p


class FakeGitHub:
    """Faux transport : enregistre les requetes et repond comme l'API GitHub."""

    def __init__(self, fail_network=0, issue_status=201, label_error=False, ff_conflicts=0):
        self.calls = []
        self.fail_network = fail_network
        self.issue_status = issue_status
        self.label_error = label_error
        self.ff_conflicts = ff_conflicts

    def __call__(self, method, url, headers, body, timeout):
        payload = json.loads(body.decode("utf-8")) if body else None
        self.calls.append({"method": method, "url": url, "headers": dict(headers), "payload": payload,
                           "timeout": timeout})
        if self.fail_network:
            self.fail_network -= 1
            raise ConnectionResetError("coupure avec %s" % TOKEN)      # ne doit jamais ressortir
        path = urllib.parse.urlparse(url).path
        base = "/repos/%s" % REPO
        if method == "PUT" and path.startswith(base + "/contents/"):
            p = urllib.parse.unquote(path[len(base + "/contents/"):])
            return 201, {}, json.dumps({"content": {
                "path": p, "html_url": "https://github.com/%s/blob/main/%s" % (REPO, p)}}).encode()
        if method == "GET" and path == base:
            return 200, {}, json.dumps({"default_branch": "main"}).encode()
        if method == "POST" and path == base + "/git/blobs":
            return 201, {}, json.dumps({"sha": "blob%d" % len(self.calls)}).encode()
        if method == "GET" and path == base + "/git/ref/heads/main":
            return 200, {}, json.dumps({"object": {"sha": "parent%d" % len(self.calls)}}).encode()
        if method == "GET" and path.startswith(base + "/git/commits/"):
            return 200, {}, json.dumps({"tree": {"sha": "tree0"}}).encode()
        if method == "POST" and path == base + "/git/trees":
            return 201, {}, json.dumps({"sha": "tree1"}).encode()
        if method == "POST" and path == base + "/git/commits":
            return 201, {}, json.dumps({"sha": "commit1"}).encode()
        if method == "PATCH" and path == base + "/git/refs/heads/main":
            if self.ff_conflicts:
                self.ff_conflicts -= 1
                return 422, {}, json.dumps({"message": "Update is not a fast forward"}).encode()
            return 200, {}, b"{}"
        if method == "POST" and path == base + "/issues":
            if self.label_error and "labels" in payload:
                return 422, {}, json.dumps({"message": "Validation Failed", "errors": [
                    {"resource": "Label", "field": "name", "code": "invalid"}]}).encode()
            if self.issue_status != 201:
                return self.issue_status, {}, json.dumps({"message": "Bad credentials"}).encode()
            return 201, {}, json.dumps({"number": 42, "html_url": "https://github.com/%s/issues/42" % REPO}).encode()
        return 404, {}, json.dumps({"message": "Not Found"}).encode()


def no_sleep(_s):
    pass


class Base(unittest.TestCase):
    def setUp(self):
        write_config({"repo": REPO, "token": TOKEN})
        for f in ("reports.json",):
            try:
                os.remove(os.path.join(paths.data_dir(), f))
            except OSError:
                pass

    def tearDown(self):
        report._CONFIG_OVERRIDE = None

    def assertNoToken(self, *texts):
        for t in texts:
            self.assertNotIn(TOKEN, json.dumps(t) if not isinstance(t, str) else t)


class Anonymisation(unittest.TestCase):
    def test_chemins(self):
        with mock.patch.dict(os.environ, FAKE_ENV):
            self.assertEqual(anonymize.text(r"C:\Users\Zorglub\AppData\Local\ebonhold"),
                             r"C:\Users\***\AppData\Local\ebonhold")
            self.assertEqual(anonymize.text("d:/Users/Jean Dupont/Jeux/Wow.exe"), "d:/Users/***/Jeux/Wow.exe")
            self.assertEqual(anonymize.text(r'{"p": "C:\\Users\\Autre\\x"}'), r'{"p": "C:\\Users\\***\\x"}')
            self.assertEqual(anonymize.text(r"loaded C:\Users\Martin (ok)"), r"loaded C:\Users\*** (ok)")
            self.assertEqual(anonymize.text(r"C:\Users\Public\Desktop"), r"C:\Users\Public\Desktop")

    def test_noms_partout(self):
        with mock.patch.dict(os.environ, FAKE_ENV):
            t = anonymize.text("Bonjour zorglub, ton PC PC-ZORGLUB ; mail zorg.lub+wow@exemple.fr",
                               accounts=["COMPTE1"])
        self.assertNotIn("orglub", t.lower())
        self.assertIn("<e-mail>", t)
        with mock.patch.dict(os.environ, FAKE_ENV):
            self.assertEqual(anonymize.text("compte COMPTE1 ok", accounts=["COMPTE1"]), "compte <compte> ok")

    def test_profil_hors_users(self):
        env = dict(FAKE_ENV, USERPROFILE=r"D:\Profils\zb", USERNAME="zb")
        with mock.patch.dict(os.environ, env):
            self.assertEqual(anonymize.text(r"D:\Profils\zb\Jeu"), r"D:\Profils\***\Jeu")


class InfosDuJeu(unittest.TestCase):
    def setUp(self):
        with mock.patch.dict(os.environ, FAKE_ENV):
            self.info = gameinfo.collect(GAME)
            self.text = gameinfo.to_text(self.info)

    def test_aucun_compte_ni_nom(self):
        blob = self.text + json.dumps(self.info)
        for secret in ("COMPTESECRET", "AUTRECOMPTE", "Zorglub", "ZORGLUB", "zorglub@", "lastCharacterIndex",
                       "accountName", "accountList", "accounttype", "NE PAS JOINDRE", "Intel"):
            self.assertNotIn(secret, blob, secret)
        self.assertIn("<compte>", self.text)                 # nom de compte masque dans ebonhold.log

    def test_reglages_utiles(self):
        cfg = self.info["config"]
        self.assertEqual(cfg["locale"], "frFR")
        self.assertEqual(cfg["realmList"], "logon.project-ebonhold.com")
        self.assertEqual(cfg["gxApi"], "d3d9")
        self.assertEqual(set(cfg), {"locale", "realmList", "gxWindow", "gxResolution", "gxApi"})

    def test_mpq_et_langues(self):
        names = [m["name"] for m in self.info["mpq"]]
        self.assertEqual(names, ["common.MPQ", "patch-5.MPQ"])
        p5 = self.info["mpq"][1]
        import hashlib
        self.assertEqual(p5["sha256"], hashlib.sha256(b"patch5").hexdigest())
        self.assertNotIn("sha256", self.info["mpq"][0])          # pas un patch
        fr = [l for l in self.info["locales"] if l["name"] == "frFR"][0]
        self.assertEqual(fr["realmlist"], "logon.project-ebonhold.com")
        self.assertEqual([m["name"] for m in fr["mpq"]], ["patch-frFR-4.MPQ"])

    def test_addons(self):
        a = {x["name"]: x for x in self.info["addons"]}
        self.assertEqual(a["MonAddon"]["version"], "1.2.3")
        self.assertEqual(a["MonAddon"]["interface"], "30300")
        self.assertEqual(a["MonAddon"]["title"], "Mon Addon")
        self.assertFalse(a["SansToc"]["toc"])
        self.assertNotIn("Blizzard_AuctionUI", a)
        self.assertEqual(self.info["blizzard_addons"], 1)

    def test_journaux(self):
        logs = {l["name"]: l for l in self.info["logs"]}
        self.assertEqual(len(logs["ebonhold.log"]["lines"]), 80)
        self.assertEqual(len(logs["Logs\\FrameXML.log"]["lines"]), 60)
        self.assertIn("Logs\\GlueXML.log", logs)
        self.assertNotIn("Logs\\connection.log", logs)
        err = [l for l in self.info["logs"] if l["name"].startswith("Errors\\")]
        self.assertEqual(err[0]["name"], "Errors\\2026-10-20 crash.txt")
        self.assertTrue(any("ERROR #132" in l for l in err[0]["lines"]))
        self.assertFalse(any(l.startswith(("User:", "Computer:", "Processor:")) for l in err[0]["lines"]))
        self.assertIn(r"C:\Users\***\AppData\Local\Ebonhold\ClientExt.dll", self.text)

    def test_dossier_absent(self):
        info = gameinfo.collect(os.path.join(_TMP, "rien"))
        self.assertFalse(info["found"])
        self.assertIn("introuvable", gameinfo.to_text(info))


@unittest.skipUnless(os.path.isdir(REAL_GAME), "jeu absent de ce PC")
class VraiJeu(unittest.TestCase):
    def test_vrai_dossier_en_lecture_seule(self):
        def snapshot():
            out = {}
            for d in (REAL_GAME, os.path.join(REAL_GAME, "Data"), os.path.join(REAL_GAME, "WTF")):
                try:
                    for e in os.scandir(d):
                        st = e.stat()
                        out[e.path] = (st.st_size, st.st_mtime_ns)
                except OSError:
                    pass
            return out
        before = snapshot()
        info = gameinfo.collect(REAL_GAME)
        text = gameinfo.to_text(info)
        self.assertEqual(before, snapshot())                      # rien n'a ete modifie
        self.assertIn("Wow.exe : version 3.3.5", text)
        low = (text + json.dumps(info)).lower()
        for n in anonymize.machine_names():
            if len(n) >= 3:
                self.assertNotIn(n.lower(), low, "nom de la machine ou de l'utilisateur dans les infos")
        self.assertIsNone(re.search(r"(?i)\\users\\(?!\*\*\*|public)", text))
        for k in ("accountname", "accountlist", "lastcharacterindex"):
            self.assertNotIn(k, low)


class AntiSpam(Base):
    def test_trois_par_heure(self):
        now = time.time()
        self.assertEqual(report.wait_minutes(now), 0)
        for i in range(3):
            report._record_sent("bug", i, now - 600 + i)
        w = report.wait_minutes(now)
        self.assertTrue(50 <= w <= 51, w)                       # le plus ancien libere sa place dans 50 min
        self.assertEqual(report.wait_minutes(now + 3000), 0)
        r = report.info("bug", GAME)
        self.assertFalse(r["can_send"])
        self.assertIn("Réessaie dans", r["message"])
        res = report.send("bug", "Un texte assez long", [], False, GAME, transport=FakeGitHub(), sleep=no_sleep)
        self.assertFalse(res["ok"])
        self.assertIn("Réessaie", res["error"])

    def test_fichier_abime(self):
        touch(os.path.join(paths.data_dir(), "reports.json"), b"{abime")
        self.assertEqual(report.wait_minutes(), 0)


class JetonMasque(Base):
    def test_aller_retour_et_config(self):
        from core import secret
        faux = "github_pat_" + "Ab9" * 25
        x = secret.masquer(faux)
        self.assertNotIn("github_pat_", x)
        self.assertEqual(secret.demasquer(x), faux)
        write_config({"repo": "Squall98/Ebonhold-Signalements", "branch": "main", "token_x": x})
        self.assertEqual(report.load_config()["token"], faux)
        write_config({"repo": "Squall98/Ebonhold-Signalements", "token_x": "pas du base64 !"})
        self.assertIsNone(report.load_config())


class Verifications(Base):
    def test_texte(self):
        self.assertIn("10 caractères", report.validate("bug", "  court   ", []))
        self.assertIn("ton idée", report.validate("suggestion", "court", []))
        self.assertEqual(report.validate("bug", "x" * 10, []), "")
        self.assertEqual(report.validate("bug", "x" * 200000, []), "")          # pas de maximum
        self.assertIn("inconnu", report.validate("autre", "x" * 20, []))

    def test_pieces_jointes(self):
        d = os.path.join(_TMP, "pj")
        png = touch(os.path.join(d, "capture.png"), PNG)
        mp4 = touch(os.path.join(d, "video.mp4"), MP4)
        exe = touch(os.path.join(d, "virus.exe"), b"MZ")
        faux = touch(os.path.join(d, "faux.png"), b"MZ pas une image")
        vide = touch(os.path.join(d, "vide.jpg"), b"")
        gros = os.path.join(d, "gros.mp4")
        with open(gros, "wb") as f:
            f.write(MP4)
            f.truncate(report.MAX_FILE_SIZE + 1)
        self.assertEqual(report.validate("bug", "x" * 20, [png, {"path": mp4}]), "")
        self.assertIn("images et les vidéos", report.validate("bug", "x" * 20, [exe]))
        self.assertIn("n'est pas une image", report.validate("bug", "x" * 20, [faux]))
        self.assertIn("vide", report.validate("bug", "x" * 20, [vide]))
        self.assertIn("trop gros", report.validate("bug", "x" * 20, [gros]))
        self.assertIn("introuvable", report.validate("bug", "x" * 20, [os.path.join(d, "absent.png")]))
        self.assertIn("deux fois", report.validate("bug", "x" * 20, [png, png]))
        many = [touch(os.path.join(d, "c%d.png" % i), PNG) for i in range(9)]
        self.assertIn("8 pièces jointes", report.validate("bug", "x" * 20, many))

    def test_nom_nettoye(self):
        with mock.patch.dict(os.environ, FAKE_ENV):
            self.assertEqual(report.clean_name(r"C:\x\Capture d'écran Zorglub (2).PNG", 1),
                             "1-Capture-d-ecran-2.png")
        self.assertEqual(report.clean_name("....", 2), "2-fichier")

    def test_titre(self):
        t = report.make_title("suggestion", "Ajouter   un bouton\n@quelqu'un " + "x" * 100)
        self.assertTrue(t.startswith("[Id\u00e9e] Ajouter un bouton @\u200bquelqu"))
        self.assertTrue(t.endswith("..."))
        self.assertTrue(report.make_title("bug", "Le jeu plante").startswith("[Bug] Le jeu plante"))


class Envoi(Base):
    def files(self):
        d = os.path.join(_TMP, "envoi")
        return [touch(os.path.join(d, "Ma capture.png"), PNG), touch(os.path.join(d, "clip.mp4"), MP4)]

    def test_requetes_github(self):
        touch(os.path.join(paths.data_dir(), "launcher.log"),
              ("\n".join("2026-10-20 ligne %d" % i for i in range(150)) +
               "\n2026-10-20 dossier C:\\Users\\Zorglub\\Jeu").encode())
        gh = FakeGitHub()
        progress = []
        with mock.patch.dict(os.environ, FAKE_ENV):
            res = report.send("bug", "Le jeu plante quand j'ouvre la carte.", self.files(), True, GAME,
                              extra={"launcher_version": "2.0.0", "catalog_source": "github",
                                     "addons": [{"id": "checkpoints", "name": "Checkpoints", "version": "1.3"}]},
                              progress=lambda p, m: progress.append((p, m)), transport=gh, sleep=no_sleep)
        self.assertTrue(res["ok"], res)
        self.assertEqual(res["number"], 42)
        self.assertIn("#42", res["message"])
        self.assertEqual([c["method"] for c in gh.calls], ["PUT", "PUT", "POST"])
        for c in gh.calls:
            h = c["headers"]
            self.assertEqual(h["Authorization"], "Bearer " + TOKEN)
            self.assertEqual(h["Accept"], "application/vnd.github+json")
            self.assertEqual(h["X-GitHub-Api-Version"], "2022-11-28")
            self.assertTrue(h["User-Agent"].startswith("EbonholdLauncher/"))
            self.assertTrue(c["url"].startswith("https://api.github.com/repos/%s/" % REPO))
        put = gh.calls[0]
        m = re.match(r"^https://api\.github\.com/repos/%s/contents/rapports/(\d{4}-\d{2}-\d{2})/"
                     r"(\d{6}-[0-9a-f]{6})/1-Ma-capture\.png$" % re.escape(REPO), put["url"])
        self.assertTrue(m, put["url"])
        self.assertEqual(m.group(1), time.strftime("%Y-%m-%d"))
        self.assertEqual(base64.b64decode(put["payload"]["content"]), PNG)
        self.assertTrue(gh.calls[1]["url"].endswith("/2-clip.mp4"))
        issue = gh.calls[2]["payload"]
        self.assertEqual(issue["title"], "[Bug] Le jeu plante quand j'ouvre la carte.")
        self.assertEqual(issue["labels"], ["bug", "launcher"])
        body = issue["body"]
        self.assertIn("Le jeu plante quand j'ouvre la carte.", body)
        self.assertIn("![1-Ma-capture.png](https://github.com/%s/blob/main/rapports/" % REPO, body)
        self.assertIn("?raw=true)", body)
        self.assertIn("[2-clip.mp4](https://github.com/%s/blob/main/rapports/" % REPO, body)
        self.assertIn("<details><summary>Infos du jeu et du launcher</summary>", body)
        self.assertIn("<details><summary>Journal du launcher (100 dernières lignes", body)
        self.assertIn("Version du launcher : 2.0.0", body)
        self.assertIn("Checkpoints | 1.3", body)
        self.assertIn("ligne 149", body)
        self.assertNotIn("ligne 49\n", body)
        self.assertIn(r"C:\Users\***\Jeu", body)
        for secret in ("Zorglub", "COMPTESECRET", TOKEN):
            self.assertNotIn(secret, body)
        self.assertLessEqual(len(body), 65536)
        self.assertNoToken(res, progress, [c["url"] for c in gh.calls])
        self.assertEqual(progress[-1][0], 100)
        self.assertEqual(report.wait_minutes(), 0)          # 1 envoi sur 3
        self.assertEqual(len(report._load_sent()), 1)

    def test_sans_journal_et_suggestion(self):
        gh = FakeGitHub()
        res = report.send("suggestion", "Une idee de bouton en plus", [], False, GAME, transport=gh, sleep=no_sleep)
        self.assertTrue(res["ok"])
        self.assertEqual(len(gh.calls), 1)
        issue = gh.calls[0]["payload"]
        self.assertTrue(issue["title"].startswith("[Id\u00e9e] "))
        self.assertEqual(issue["labels"], ["suggestion", "launcher"])
        self.assertNotIn("Journal du launcher", issue["body"])
        self.assertNotIn("ebonhold.log", issue["body"])          # pas de journaux du jeu pour une idee

    def test_gros_fichier_par_git_data(self):
        gh = FakeGitHub(ff_conflicts=1)
        with mock.patch.object(report, "CONTENTS_MAX", 32):
            res = report.send("bug", "Video du bug en piece jointe", self.files(), False, GAME,
                              transport=gh, sleep=no_sleep)
        self.assertTrue(res["ok"], res)
        seq = [(c["method"], urllib.parse.urlparse(c["url"]).path.split(REPO, 1)[1]) for c in gh.calls]
        self.assertEqual(seq[:3], [("GET", ""), ("POST", "/git/blobs"), ("POST", "/git/blobs")])
        # un premier PATCH refuse (envoi simultane) -> on recommence a partir de la branche
        self.assertEqual([m for m, _p in seq[3:-1]],
                         ["GET", "GET", "POST", "POST", "PATCH", "GET", "GET", "POST", "POST", "PATCH"])
        self.assertEqual(seq[-1], ("POST", "/issues"))
        blob = gh.calls[1]["payload"]
        self.assertEqual(blob["encoding"], "base64")
        self.assertEqual(base64.b64decode(blob["content"]), PNG)
        tree = [c for c in gh.calls if c["url"].endswith("/git/trees")][0]["payload"]
        self.assertEqual(tree["base_tree"], "tree0")
        self.assertEqual([t["path"].rsplit("/", 1)[1] for t in tree["tree"]], ["1-Ma-capture.png", "2-clip.mp4"])
        self.assertEqual(gh.calls[-2]["payload"], {"sha": "commit1", "force": False})
        self.assertIn("/blob/main/rapports/", gh.calls[-1]["payload"]["body"])

    def test_reseau_trois_essais(self):
        gh = FakeGitHub(fail_network=2)
        res = report.send("bug", "Le jeu plante au demarrage", [], False, GAME, transport=gh, sleep=no_sleep)
        self.assertTrue(res["ok"], res)
        self.assertEqual(len(gh.calls), 3)

    def test_reseau_coupe(self):
        gh = FakeGitHub(fail_network=99)
        res = report.send("bug", "Le jeu plante au demarrage", [], False, GAME, transport=gh, sleep=no_sleep)
        self.assertFalse(res["ok"])
        self.assertEqual(len(gh.calls), 3)
        self.assertIn("Réessaie plus tard", res["error"])
        self.assertNoToken(res)
        with open(os.path.join(paths.data_dir(), "launcher.log"), encoding="utf-8") as f:
            self.assertNotIn(TOKEN, f.read())
        self.assertEqual(report._load_sent(), [])             # un echec ne compte pas dans l'anti-spam

    def test_jeton_refuse(self):
        res = report.send("bug", "Le jeu plante au demarrage", [], False, GAME,
                          transport=FakeGitHub(issue_status=401), sleep=no_sleep)
        self.assertFalse(res["ok"])
        self.assertIn("clé d'envoi", res["error"])
        self.assertNoToken(res)

    def test_etiquettes_absentes(self):
        gh = FakeGitHub(label_error=True)
        res = report.send("bug", "Le jeu plante au demarrage", [], False, GAME, transport=gh, sleep=no_sleep)
        self.assertTrue(res["ok"], res)
        self.assertEqual(len(gh.calls), 2)
        self.assertNotIn("labels", gh.calls[1]["payload"])

    def test_texte_tres_long(self):
        gh = FakeGitHub()
        text = "Description tres detaillee. " * 4000              # ~112 000 caracteres
        res = report.send("bug", text, [], True, GAME, transport=gh, sleep=no_sleep)
        self.assertTrue(res["ok"], res)
        put = gh.calls[0]
        self.assertTrue(put["url"].endswith("/signalement-complet.md"))
        self.assertIn(text.strip(), base64.b64decode(put["payload"]["content"]).decode("utf-8"))
        body = gh.calls[1]["payload"]["body"]
        self.assertLessEqual(len(body), 65536)
        self.assertIn("signalement-complet.md", body)

    def test_sans_configuration(self):
        report._CONFIG_OVERRIDE = os.path.join(_TMP, "absent.json")
        r = report.info("bug", GAME)
        self.assertFalse(r["can_send"])
        self.assertEqual(r["message"], report.UNAVAILABLE)
        res = report.send("bug", "Le jeu plante au demarrage", [], False, GAME, transport=FakeGitHub())
        self.assertEqual(res["error"], report.UNAVAILABLE)
        write_config({"repo": "pas un depot", "token": TOKEN})
        self.assertIsNone(report.load_config())

    def test_info(self):
        touch(os.path.join(paths.data_dir(), "launcher.log"), b"2026-10-20 demarrage\n")
        r = report.info("bug", GAME, extra={"launcher_version": "2.0.0", "fr_settings": {"jeu": "fr", "voix": "en"},
                                            "fr_state": {"applied": True}})
        self.assertTrue(r["can_send"])
        self.assertEqual(r["wait_minutes"], 0)
        self.assertTrue(r["log_available"])
        self.assertIn("== Launcher ==", r["infos_preview"])
        self.assertIn("Réglages FR : jeu=fr ; voix=en", r["infos_preview"])
        self.assertIn("État du patch FR : applied=oui", r["infos_preview"])
        self.assertIn("== Patchs (Data) ==", r["infos_preview"])
        self.assertNotIn("COMPTESECRET", r["infos_preview"])

    def test_pas_de_jeton_dans_les_redirections(self):
        captured = {}

        class Resp:
            status = 201
            headers = {}

            def read(self):
                return b"{}"

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake_urlopen(req, timeout):
            captured["req"] = req
            return Resp()
        with mock.patch("urllib.request.urlopen", fake_urlopen):
            report.urllib_transport("POST", "https://api.github.com/x", {"Authorization": "Bearer " + TOKEN,
                                                                       "Accept": "a"}, b"{}", 5)
        req = captured["req"]
        self.assertEqual(req.unredirected_hdrs.get("Authorization"), "Bearer " + TOKEN)
        self.assertNotIn("Authorization", req.headers)


class Captures(Base):
    def test_captures_recentes(self):
        shots = os.path.join(GAME, "Screenshots")
        now = time.time()
        for i in range(12):
            p = touch(os.path.join(shots, "WoWScrnShot_%02d.jpg" % i), JPG)
            os.utime(p, (now - 1000 + i, now - 1000 + i))
        touch(os.path.join(shots, "notes.txt"), b"x")
        tga = touch(os.path.join(shots, "ancien.tga"), b"\x00\x00\x02" + b"\x00" * 30)
        os.utime(tga, (now, now))
        items = report.recent_captures(GAME, include_windows=False)
        self.assertEqual(len(items), 10)
        self.assertEqual(items[0]["name"], "ancien.tga")
        self.assertEqual(items[1]["name"], "WoWScrnShot_11.jpg")
        self.assertEqual(set(items[0]), {"path", "name", "date", "size", "size_label", "source", "mtime"})
        self.assertEqual(items[0]["source"], "jeu")
        self.assertEqual(report.validate("bug", "x" * 20, [tga]), "")         # TGA du jeu acceptee

    def test_vignette(self):
        d = os.path.join(_TMP, "vignettes")
        png = touch(os.path.join(d, "a.png"), PNG)
        self.assertTrue(report.thumbnail(png).startswith("data:image/png;base64,"))
        self.assertIsNone(report.thumbnail(touch(os.path.join(d, "b.png"), b"pas une image")))
        self.assertIsNone(report.thumbnail(touch(os.path.join(d, "c.txt"), PNG)))
        self.assertIsNone(report.thumbnail(os.path.join(d, "absent.png")))
        big = touch(os.path.join(d, "gros.png"), PNG + b"\x00" * report.THUMB_MAX)
        try:
            import PIL  # noqa: F401
        except ImportError:
            self.assertIsNone(report.thumbnail(big))       # sans Pillow : trop gros -> pas d'apercu


def tearDownModule():
    report._CONFIG_OVERRIDE = None
    shutil.rmtree(_TMP, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
