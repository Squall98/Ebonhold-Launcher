# -*- coding: utf-8 -*-
"""API Python exposee au frontend JS via pywebview (window.pywebview.api.*).

Toutes les operations longues (install/maj) tournent dans un thread et poussent
leur progression au JS via window.evaluate_js(onProgress / onDone).
"""
import json
import os
import queue
import shutil
import subprocess
import threading
import time
import urllib.parse
import webbrowser

from . import catalog, frconfig, frpack, gamescan, installer, prefs, report, selfupdate, state, version, wow
from .journal import log

# Pieces jointes acceptees par la fenetre « Signaler » (images et videos).
_ATTACH_FILTER = ("Images et vidéos (*.png;*.jpg;*.jpeg;*.gif;*.bmp;*.webp;*.tga;"
                  "*.mp4;*.webm;*.mov;*.mkv)",)

# Produits geres par l'onglet Francais (installes / retires selon les reglages).
FR_ADDON = "ebonholdfr"
MANAGED = {FR_ADDON}

# Liens que le launcher accepte d'ouvrir : du web, et seulement ces sites.
_URL_HOSTS = ("github.com", "raw.githubusercontent.com", "squall98.github.io",
              "discord.gg", "discord.com", "drive.google.com")


def _url_ok(url):
    try:
        u = urllib.parse.urlparse(str(url))
    except ValueError:
        return False
    host = (u.hostname or "").lower()
    return u.scheme == "https" and any(host == h or host.endswith("." + h) for h in _URL_HOSTS)


def _throttled(send, every=0.1):
    """Limite une progression (pct, msg) a ~10 envois par seconde ; 100 % passe toujours."""
    last = [0.0]

    def progress(pct, msg):
        now = time.monotonic()
        if pct >= 100 or now - last[0] >= every:
            last[0] = now
            send(pct, msg)
    return progress


def _status(product, installed_version):
    if installed_version is None:
        return "install"
    if version.normalize(installed_version) == version.normalize(product["version"]):
        return "uptodate"
    if version.is_newer(product["version"], installed_version):
        return "update"
    return "uptodate"  # version sur disque >= catalogue -> considere a jour


class Api:
    def __init__(self):
        self._window = None          # injecte par main.py ; prefixe _ OBLIGATOIRE :
        # pywebview introspecte tout attribut PUBLIC non-callable du js_api au boot et
        # recurse dans l'objet fenetre WebView2 natif (-> "maximum recursion depth" +
        # blocage de plusieurs minutes). Les noms en _ sont ignores par get_functions().
        self._manifest = None
        self._source = None
        # File d'installation : un seul produit a la fois (jamais deux ecritures en parallele
        # dans AddOns ni dans state.json).
        self._queue = queue.Queue()
        self._queued = set()
        self._qlock = threading.Lock()
        self._worker = None
        self._startup_done = False
        self._fr_busy = threading.Lock()   # une seule application des reglages FR a la fois
        self._scan_busy = threading.Lock()     # une seule recherche du jeu a la fois
        self._scan_cancel = threading.Event()
        self._report_busy = threading.Lock()   # un seul envoi de signalement a la fois

    # ----------------------------------------------------------- catalogue
    def get_catalog(self, check_remote=False):
        """Retourne l'etat complet pour l'UI, INSTANTANEMENT (sans reseau).

        Au premier appel : dernier catalogue en ligne garde sur le disque, sinon catalogue
        embarque. Ensuite on GARDE le catalogue deja charge (un rechargement apres une
        installation ne doit pas revenir au catalogue embarque, plus ancien).
        Si check_remote=True, on verifie le catalogue en ligne EN ARRIERE-PLAN (thread)
        et on pousse la mise a jour au JS via onCatalogUpdate quand elle est prete.
        """
        if self._manifest is None:
            self._manifest, self._source = catalog.fetch_offline()
            log("catalogue au demarrage : %s" % self._source)
        resp = self._build_catalog()
        if check_remote:
            threading.Thread(target=self._remote_refresh, daemon=True).start()
        if not self._startup_done:
            self._startup_done = True
            threading.Thread(target=self._startup_checks, daemon=True).start()
        # Detection du dossier WoW en ARRIERE-PLAN si aucun n'est enregistre : autodetect
        # peut tester des disques lents/deconnectes, ce qui bloquerait get_catalog.
        if not state.get_wow_path():
            threading.Thread(target=self._detect_wow, daemon=True).start()
        return resp

    def _remote_refresh(self):
        """Recupere le manifeste en ligne en fond ; pousse onCatalogUpdate si dispo."""
        try:
            man = catalog._load_remote()
        except Exception as e:
            log("catalogue en ligne injoignable : %r" % e)
            return  # hors-ligne ou repo injoignable -> on garde le local, sans bloquer
        self._manifest, self._source = man, "remote"
        log("catalogue en ligne recu (%d produits, launcher %s)" % (
            len(catalog.products(man)), catalog.launcher_version(man)))
        self._emit("onCatalogUpdate", self._build_catalog())
        self._maj_addon_fr()

    def _maj_addon_fr(self):
        """EbonholdFR n'a pas de carte dans le catalogue : s'il est installe et qu'une version
        plus recente est en ligne, on l'installe tout de suite (jeu ferme), avec ses reglages."""
        try:
            wow_path = state.get_wow_path()
            product = self._find(FR_ADDON)
            entry = state.get_installed(FR_ADDON)
            if not (product and entry and wow.is_valid_install(wow_path)):
                return
            if _status(product, entry["version"]) == "uptodate" and not installer.is_broken(FR_ADDON, wow_path):
                return
            if wow.game_running() or not self._fr_busy.acquire(blocking=False):
                log("EbonholdFR v%s : mise a jour au prochain demarrage (jeu ouvert ou reglages en cours)"
                    % product["version"])
                return
            try:
                log("EbonholdFR : mise a jour automatique vers v%s" % product["version"])
                installer.install(product, wow_path)
                ok, _ = frconfig.is_available()
                if ok:
                    self._ecrire_reglages_addon(wow_path, frconfig._fr_patch().normaliser(
                        frconfig.reglages_enregistres()))
            finally:
                self._fr_busy.release()
            self._emit("onCatalogUpdate", self._build_catalog())
        except Exception as e:
            log("echec mise a jour EbonholdFR : %r" % e)

    def _detect_wow(self):
        """Detecte le dossier WoW en fond (peut scanner des disques) et rafraichit l'UI
        si on en trouve un. Jamais sur le chemin bloquant de get_catalog/_build_catalog."""
        path = ""
        try:
            # Emplacements connus, registre, raccourcis (pas de parcours des disques : ca,
            # c'est scan_games, apres accord du joueur). Ebonhold avec Wow.exe d'abord.
            for c in gamescan.quick_detect():
                if c.get("is_ebonhold") and c.get("has_exe") and wow.is_valid_install(c["path"]):
                    path = c["path"]
                    break
        except Exception as e:
            log("detection rapide du jeu impossible : %r" % e)
        try:
            path = path or wow.autodetect()
        except Exception:
            return
        if path and not state.get_wow_path():
            state.set_wow_path(path)
            self._emit("onCatalogUpdate", self._build_catalog())

    def _build_catalog(self):
        """Construit la reponse catalogue a partir de self._manifest (sans reseau).

        N'appelle PAS wow.autodetect() ici : la detection (qui peut scanner des disques
        lents) tourne en arriere-plan (_detect_wow) pour ne jamais bloquer get_catalog.
        """
        wow_path = state.get_wow_path()
        wow_valid = wow.is_valid_install(wow_path)
        items = []
        updates = 0
        by_id = {}
        for p in catalog.products(self._manifest):
            entry = state.get_installed(p["id"])
            if entry:
                installed_version = entry["version"]
            else:
                installed_version = None
                if wow_valid:
                    dv = installer.disk_version(p, wow_path)
                    if dv is not None:                       # deja present (pose a la main)
                        installed_version = dv or p["version"]
            st = _status(p, installed_version)
            # Un mod installe dont des fichiers ont disparu -> a reparer.
            if installed_version is not None and wow_valid and installer.is_broken(p["id"], wow_path):
                st = "repair"
            # "install" (jamais installe) n'est pas une MAJ ; EbonholdFR (gere par l'onglet
            # Francais, invisible dans le catalogue) se met a jour tout seul (_maj_addon_fr).
            if st in ("update", "repair") and p["id"] not in MANAGED:
                updates += 1
            row = {
                "id": p["id"],
                "managed": p["id"] in MANAGED,    # gere par l'onglet Francais, pas une carte du catalogue
                "name": p["name"],
                "category": p["category"],
                "description": p.get("description", ""),
                "long_description": p.get("long_description", ""),
                "version": p["version"],
                "installed_version": installed_version,
                "status": st,
                "notes": p.get("notes", ""),
                "history": p.get("history", []),
                "changelog_url": p.get("changelog_url", ""),
                "icon": p.get("icon", ""),        # icone Tabler optionnelle (ex: "ti-shield")
                "accent": p.get("accent", ""),    # couleur de carte optionnelle (purple/teal/...)
            }
            items.append(row)
            by_id[p["id"]] = row

        # Packs : statut derive de l'etat de leurs produits.
        packs = []
        for pk in self._manifest.get("packs", []):
            sub = [by_id[i] for i in pk.get("products", []) if i in by_id]
            done = sum(1 for s in sub if s["status"] == "uptodate")
            packs.append({
                "id": pk["id"], "name": pk["name"], "description": pk.get("description", ""),
                "icon": pk.get("icon", "ti-package"), "accent": pk.get("accent", "purple"),
                "products": pk.get("products", []),
                "total": len(sub), "done": done,
                "status": "complete" if sub and done == len(sub) else "install",
            })

        manifest_lv = catalog.launcher_version(self._manifest)
        return {
            "source": self._source,
            "launcher_version": version.APP_VERSION,
            "latest_launcher_version": manifest_lv,
            "launcher_update": version.is_newer(manifest_lv, version.APP_VERSION),
            "launcher_download_url": self._manifest.get("launcher_download_url", ""),
            "launcher_frozen": selfupdate.is_frozen(),
            "categories": self._manifest.get("categories", []),
            "packs": packs,
            "links": self._manifest.get("links", []),
            "updates_count": updates,
            "wow_path": wow_path,
            "wow_valid": wow_valid,
            "products": items,
        }

    # --------------------------------------------------------- dossier WoW
    def choose_folder(self):
        """Ouvre le selecteur natif de dossier et memorise le choix s'il est valide."""
        import webview
        result = self._window.create_file_dialog(webview.FileDialog.FOLDER)
        if not result:
            return {"ok": False, "path": state.get_wow_path()}
        path = result[0]
        if not wow.is_valid_install(path):
            return {"ok": False, "path": path,
                    "error": "Ce dossier n'est pas une installation du jeu (Data\\ introuvable)."}
        state.set_wow_path(path)
        return {"ok": True, "path": path}

    def quick_detect(self):
        """Installations trouvees sans parcourir les disques (instantane)."""
        try:
            return {"candidates": gamescan.quick_detect()}
        except Exception as e:
            log("detection rapide impossible : %r" % e)
            return {"candidates": []}

    def scan_games(self):
        """Recherche du jeu sur les disques (apres accord du joueur) : onScanProgress puis onScanDone."""
        if not self._scan_busy.acquire(blocking=False):
            return {"started": False, "error": "Recherche déjà en cours."}

        self._scan_cancel.clear()

        def worker():
            cands = []
            try:
                cands = gamescan.scan(progress=lambda m: self._emit("onScanProgress", m),
                                      cancel=self._scan_cancel)
            except Exception as e:
                log("recherche du jeu impossible : %r" % e)
            finally:
                self._scan_busy.release()
            log("recherche du jeu : %d dossier(s) trouve(s)" % len(cands))
            self._emit("onScanDone", cands)

        threading.Thread(target=worker, daemon=True).start()
        return {"started": True}

    def cancel_scan(self):
        self._scan_cancel.set()
        return {"ok": True}

    def set_wow_path(self, path):
        """Dossier choisi dans la liste des installations trouvees."""
        if not wow.is_valid_install(path):
            return {"ok": False, "error": "Ce dossier n'est pas une installation du jeu (Data\\ introuvable)."}
        state.set_wow_path(path)
        log("dossier du jeu choisi")
        if self._manifest is not None:
            self._emit("onCatalogUpdate", self._build_catalog())
        return {"ok": True, "path": path}

    # ------------------------------------------------------------ preferences
    def get_prefs(self):
        return prefs.get()

    def set_pref(self, key, value):
        return prefs.set(key, value)

    # ----------------------------------------------------- install / update
    def install_product(self, product_id):
        """Met l'installation/maj dans la file (traitee en arriere-plan, une a la fois).
        La progression arrive via onProgress/onDone."""
        product = self._find(product_id)
        if product is None:
            return {"started": False, "error": "Produit inconnu."}
        if not wow.is_valid_install(state.get_wow_path()):
            return {"started": False, "error": "Choisis d'abord ton dossier Ebonhold."}
        with self._qlock:
            if product_id not in self._queued:
                self._queued.add(product_id)
                self._queue.put(product_id)
            if self._worker is None or not self._worker.is_alive():
                self._worker = threading.Thread(target=self._run_queue, daemon=True)
                self._worker.start()
        return {"started": True}

    def _run_queue(self):
        while True:
            try:
                product_id = self._queue.get(timeout=1)
            except queue.Empty:
                with self._qlock:
                    if self._queue.empty():
                        self._worker = None
                        return
                continue
            try:
                self._install_one(product_id)
            finally:
                with self._qlock:
                    self._queued.discard(product_id)

    def _install_one(self, product_id):
        product = self._find(product_id)
        wow_path = state.get_wow_path()
        if product is None or not wow.is_valid_install(wow_path):
            self._emit("onDone", product_id, False, "Produit ou dossier du jeu introuvable.")
            return
        progress = _throttled(lambda pct, msg: self._emit("onProgress", product_id, pct, msg))
        try:
            installer.install(product, wow_path, progress)
            log("installe : %s v%s" % (product_id, product["version"]))
            if product_id == FR_ADDON:      # le dossier vient d'etre remplace : ses reglages aussi
                self._ecrire_reglages_addon(wow_path, frconfig.reglages_enregistres())
            self._emit("onDone", product_id, True, "Installé (v%s)." % product["version"])
        except Exception as e:
            log("echec installation %s : %r" % (product_id, e))
            self._emit("onDone", product_id, False, str(e))

    def uninstall_product(self, product_id):
        wow_path = state.get_wow_path()
        try:
            installer.uninstall(product_id, wow_path, self._find(product_id))
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def install_all(self):
        """Met a jour (ou repare) les produits DEJA installes, un par un. N'installe jamais
        un produit que le joueur n'a pas choisi."""
        if not self._manifest:
            self.get_catalog()
        rows = self._build_catalog()["products"]
        ids = [r["id"] for r in rows if r["status"] in ("update", "repair")]
        for pid in ids:
            self.install_product(pid)
        return {"started": True, "count": len(ids), "ids": ids}

    def install_pack(self, pack_id):
        """Installe/MAJ tous les produits d'un pack qui ne sont pas a jour."""
        if not self._manifest:
            self.get_catalog()
        pack = next((p for p in self._manifest.get("packs", []) if p["id"] == pack_id), None)
        if not pack:
            return {"started": False, "error": "Pack inconnu."}
        if not wow.is_valid_install(state.get_wow_path()):
            return {"started": False, "error": "Choisis d'abord ton dossier Ebonhold."}
        started = []
        for pid in pack.get("products", []):
            product = self._find(pid)
            if not product:
                continue
            entry = state.get_installed(pid)
            iv = entry["version"] if entry else None
            if _status(product, iv) != "uptodate" or installer.is_broken(pid, state.get_wow_path()):
                self.install_product(pid)
                started.append(pid)
        return {"started": True, "ids": started}

    # ----------------------------------------------------- auto-update launcher
    def update_launcher(self):
        """Met a jour le launcher. En .exe : telecharge + remplace + relance (l'app se ferme).
        En dev (python) : renvoie l'URL a ouvrir (pas d'.exe a remplacer)."""
        url = self._manifest.get("launcher_download_url", "") if self._manifest else ""
        sha = self._manifest.get("launcher_sha256", "") if self._manifest else ""
        if not selfupdate.is_frozen():
            return {"ok": False, "mode": "dev", "url": url,
                    "error": "Disponible uniquement sur la version .exe ; page ouverte."}
        if not url or not sha:
            return {"ok": False, "mode": "exe",
                    "error": "Mise à jour indisponible (catalogue incomplet). Réessaie plus tard."}

        def worker():
            progress = _throttled(lambda pct, msg: self._emit("onLauncherProgress", pct, msg), 0.25)
            try:
                log("mise a jour du launcher : %s" % url)
                selfupdate.download_and_swap(url, sha, progress)
                self._emit("onLauncherReady")          # le JS demande la fermeture
                if self._window is not None:
                    self._window.destroy()                # quitte pour liberer l'.exe
            except Exception as e:
                log("echec mise a jour du launcher : %r" % e)
                self._emit("onLauncherError", str(e))

        threading.Thread(target=worker, daemon=True).start()
        return {"ok": True, "mode": "exe"}

    # ------------------------------------------------------- config langue FR
    def get_fr_status(self):
        ok, err = frconfig.is_available()
        wow_path = state.get_wow_path()
        if not self._manifest:
            self._manifest, self._source = catalog.fetch_offline()
        fr = self._manifest.get("fr_config", {}) if self._manifest else {}
        spec = fr.get("pack_download") or {}
        return {
            "available": ok,
            "error": err or "",
            "pack_present": frconfig.pack_present(wow_path) if (ok and wow_path) else False,
            "pack_url": fr.get("pack_url", ""),
            "pack_note": fr.get("pack_note", ""),
            "pack_installable": bool(spec.get("url") or spec.get("parts")),
        }

    def install_fr_pack(self):
        """Telecharge + installe le pack frFR en arriere-plan (onFrLog / onPackProgress / onPackDone)."""
        wow_path = state.get_wow_path()
        if not wow.is_valid_install(wow_path):
            return {"started": False, "error": "Choisis d'abord ton dossier Ebonhold."}
        if not self._manifest:
            self._manifest, self._source = catalog.fetch_offline()
        spec = (self._manifest.get("fr_config", {}) or {}).get("pack_download") or {}
        if not (spec.get("url") or spec.get("parts")):
            return {"started": False, "error": "Aucune source de pack configuree."}
        if wow.game_running():
            return {"started": False, "error": "Ferme d'abord le jeu (Wow.exe), puis recommence."}

        def worker():
            progress = _throttled(lambda pct, msg: self._emit("onPackProgress", pct, msg), 0.25)

            def flog(msg):
                log("pack FR : %s" % msg)
                self._emit("onFrLog", msg)
            try:
                frpack.install(wow_path, spec, progress, flog)
                self._emit("onPackDone", True, "Pack FR installé.")
            except Exception as e:
                log("echec pack FR : %r" % e)
                self._emit("onPackDone", False, str(e))

        threading.Thread(target=worker, daemon=True).start()
        return {"started": True}

    def apply_fr_config(self, base_fr, voices_fr, spells_fr, other_fr):
        """Applique la config langue en arriere-plan. Journal via onFrLog, fin via onFrDone."""
        wow_path = state.get_wow_path()
        if not wow.is_valid_install(wow_path):
            return {"started": False, "error": "Choisis d'abord ton dossier Ebonhold."}
        if wow.game_running():
            return {"started": False, "error": "Ferme d'abord le jeu (Wow.exe), puis recommence."}

        def worker():
            def flog(msg):
                log("patch FR : %s" % msg)
                self._emit("onFrLog", msg)
            try:
                frconfig.apply(wow_path, base_fr, voices_fr, spells_fr, other_fr, flog)
                self._emit("onFrDone", True, "Configuration appliquée. Lance le jeu.")
            except Exception as e:
                log("echec patch FR : %r" % e)
                self._emit("onFrDone", False, str(e))

        threading.Thread(target=worker, daemon=True).start()
        return {"started": True}

    # ------------------------------------------------- onglet Francais (v2)
    def _fr_addon_dir(self, wow_path):
        return os.path.join(wow.addons_dir(wow_path), "EbonholdFR")

    def _fr_addon_version(self, wow_path):
        return installer._toc_version(os.path.join(self._fr_addon_dir(wow_path), "EbonholdFR.toc"))

    def _fr_extra(self, wow_path):
        """Traductions plus recentes livrees avec l'addon EbonholdFR installe (4.0+)."""
        p = os.path.join(self._fr_addon_dir(wow_path), "data", "patch_fr.json") if wow_path else ""
        return (p,) if p and os.path.isfile(p) else ()

    def get_fr_settings(self):
        P = frconfig._fr_patch()
        wow_path = state.get_wow_path()
        if not self._manifest:
            self._manifest, self._source = catalog.fetch_offline()
        fr = self._manifest.get("fr_config", {}) or {}
        spec = fr.get("pack_download") or {}
        ok, err = frconfig.is_available()
        st = frconfig.status(wow_path, self._fr_extra(wow_path)) if (ok and wow_path) else {
            "applied": False, "up_to_date": False, "server_changed": False, "needs_pack": False,
            "last_applied": None, "message": err or "Choisis d'abord ton dossier Ebonhold."}
        return {
            "settings": frconfig.reglages_enregistres() if ok else P.normaliser({}),
            "presets": P.PRESETS,
            "available": ok, "error": err or "",
            "pack_present": frconfig.pack_present(wow_path) if (ok and wow_path) else False,
            "pack_installable": bool(spec.get("url") or spec.get("parts")),
            "pack_note": fr.get("pack_note", ""),
            "state": st,
        }

    def _ecrire_reglages_addon(self, wow_path, s):
        """Fichier lu par EbonholdFR 4.0 au demarrage du jeu (reglages choisis dans le launcher)."""
        P = frconfig._fr_patch()
        d = self._fr_addon_dir(wow_path)
        if not os.path.isdir(d):
            return
        patch = os.path.exists(os.path.join(wow_path, "Data", "patch-Z.MPQ"))
        b = lambda k: "true" if P.fr(s, k) else "false"
        lua = ("-- Ecrit par Ebonhold Launcher : reglages de l'onglet Francais. Ne pas modifier a la main.\n"
               "EbonholdFR_Reglages = { version = 1, interface = %s, echoes_desc = %s, soultree_desc = %s,\n"
               "  affixes_desc = %s, tomes = %s, nom_anglais = %s, patch = %s }\n") % (
            b("interface"), b("echoes_desc"), b("soultree_desc"), b("affixes_desc"), b("tomes"),
            "true" if s.get("nom_anglais") else "false", "true" if patch else "false")
        with open(os.path.join(d, "EbonholdFR_Reglages.lua"), "w", encoding="utf-8") as f:
            f.write(lua)

    def _gerer_addon_fr(self, wow_path, s, flog):
        """Installe (ou retire) l'addon EbonholdFR selon les reglages, puis ecrit ses reglages.
        Renvoie True si EbonholdFR 4.0+ est en place (il contient alors le correctif de la forge)."""
        P = frconfig._fr_patch()
        besoin = any(P.fr(s, k) for k in P.CLES_FR_EN if k != "voix")
        product = self._find(FR_ADDON)
        if besoin and product:
            entry = state.get_installed(FR_ADDON)
            iv = entry["version"] if entry else installer.disk_version(product, wow_path)
            if iv is None or _status(product, iv) != "uptodate" or installer.is_broken(FR_ADDON, wow_path):
                flog("Installation de l'addon EbonholdFR v%s..." % product["version"])
                installer.install(product, wow_path)
        elif not besoin and state.get_installed(FR_ADDON):
            flog("Tout est en anglais : addon EbonholdFR retiré.")
            installer.uninstall(FR_ADDON, wow_path, product)
        self._ecrire_reglages_addon(wow_path, s)
        v4 = version.is_newer(self._fr_addon_version(wow_path) or "0", "3.99")
        if v4:
            ancien = os.path.join(wow.addons_dir(wow_path), "EbonholdFRFix")
            if os.path.isdir(ancien):
                shutil.rmtree(ancien, ignore_errors=True)
                flog("Ancien correctif EbonholdFRFix retiré (intégré à EbonholdFR).")
        return v4

    def _appliquer_fr(self, wow_path, settings, flog):
        with self._fr_busy:
            P = frconfig._fr_patch()
            s = P.normaliser(settings)
            v4 = self._gerer_addon_fr(wow_path, s, flog)
            frconfig.apply_v2(wow_path, s, flog, extra=self._fr_extra(wow_path), deploy_fix=not v4)
            self._ecrire_reglages_addon(wow_path, s)      # « patch » vaut maintenant l'etat reel

    def apply_fr(self, settings):
        """Applique les reglages de l'onglet Francais en arriere-plan (onFrLog / onFrDone)."""
        wow_path = state.get_wow_path()
        if not wow.is_valid_install(wow_path):
            return {"started": False, "error": "Choisis d'abord ton dossier Ebonhold."}
        if wow.game_running():
            return {"started": False, "error": "Ferme d'abord le jeu (Wow.exe), puis recommence."}

        def worker():
            def flog(msg):
                log("patch FR : %s" % msg)
                self._emit("onFrLog", msg)
            try:
                self._appliquer_fr(wow_path, settings, flog)
                self._emit("onFrDone", True, "Réglages appliqués. Tu peux lancer le jeu.")
                self._emit("onFrState", frconfig.status(wow_path, self._fr_extra(wow_path)))
            except Exception as e:
                log("echec reglages FR : %r" % e)
                self._emit("onFrDone", False, str(e))

        threading.Thread(target=worker, daemon=True).start()
        return {"started": True}

    def _startup_checks(self):
        """Au demarrage : si le serveur a ete mis a jour (ou le patch efface), on reapplique les
        reglages FR tout seul, puis on previent l'interface."""
        try:
            wow_path = state.get_wow_path()
            if not wow.is_valid_install(wow_path):
                return
            self._maj_addon_fr()
            ok, _ = frconfig.is_available()
            if not ok:
                return
            st = frconfig.status(wow_path, self._fr_extra(wow_path))
            if not st["applied"] or st["up_to_date"]:
                return
            if st["needs_pack"] or wow.game_running():
                log("reglages FR a reappliquer plus tard : %s" % st["message"])
                self._emit("onFrState", st)
                return
            log("reapplication automatique des reglages FR : %s" % st["message"])
            self._emit("onFrLog", "Mise à jour détectée : réapplication de tes réglages FR...")
            self._appliquer_fr(wow_path, frconfig.reglages_enregistres(),
                               lambda m: log("patch FR (auto) : %s" % m))
            st2 = frconfig.status(wow_path, self._fr_extra(wow_path))
            st2["message"] = "Réglages FR réappliqués après la mise à jour."
            self._emit("onFrState", st2)
        except Exception as e:
            log("echec verification au demarrage : %r" % e)

    # ---------------------------------------------------------------- jouer
    def check_before_play(self):
        """Ce qui empeche de bien jouer : jeu deja ouvert, FR a refaire, addons a jour."""
        wow_path = state.get_wow_path()
        issues = []
        if not wow.is_valid_install(wow_path):
            return {"ok": False, "issues": [{"id": "dossier", "label": "Dossier du jeu introuvable.",
                                             "fix_label": "Choisir le dossier"}]}
        if wow.game_running():
            issues.append({"id": "deja_ouvert", "label": "Le jeu est déjà ouvert.", "fix_label": ""})
        ok, _ = frconfig.is_available()
        if ok:
            st = frconfig.status(wow_path, self._fr_extra(wow_path))
            if st["applied"] and not st["up_to_date"]:
                issues.append({"id": "fr", "label": st["message"],
                               "fix_label": "" if st["needs_pack"] else "Réappliquer le français"})
        cat = self._build_catalog()
        n = sum(1 for r in cat["products"] if r["status"] in ("update", "repair"))
        if n:
            issues.append({"id": "addons", "label": "%d addon(s) à mettre à jour." % n,
                           "fix_label": "Mettre à jour"})
        return {"ok": not issues, "issues": issues}

    def fix_issues(self, ids):
        wow_path = state.get_wow_path()

        def worker():
            try:
                if "addons" in ids:
                    for r in self._build_catalog()["products"]:
                        if r["status"] in ("update", "repair"):
                            self._install_one(r["id"])
                if "fr" in ids and not wow.game_running():
                    self._appliquer_fr(wow_path, frconfig.reglages_enregistres(),
                                       lambda m: self._emit("onFrLog", m))
                self._emit("onFixDone", True, "C'est corrigé.")
            except Exception as e:
                log("echec correction : %r" % e)
                self._emit("onFixDone", False, str(e))

        threading.Thread(target=worker, daemon=True).start()
        return {"started": True}

    # ------------------------------------------- signaler un bug / une idee
    def _report_extra(self):
        """Infos du launcher jointes au signalement (anonymisees par report)."""
        if not self._manifest:
            self._manifest, self._source = catalog.fetch_offline()
        extra = {"launcher_version": version.APP_VERSION, "catalog_source": self._source or ""}
        try:
            extra["addons"] = [{"name": r["name"], "version": r["installed_version"]}
                               for r in self._build_catalog()["products"] if r["installed_version"]]
        except Exception:
            pass
        try:
            ok, _ = frconfig.is_available()
            if ok:
                extra["fr_settings"] = frconfig.reglages_enregistres()
                wp = state.get_wow_path()
                if wow.is_valid_install(wp):
                    st = frconfig.status(wp, self._fr_extra(wp))
                    extra["fr_state"] = {"appliqué": st.get("applied"), "à jour": st.get("up_to_date"),
                                         "le": st.get("last_applied")}
        except Exception:
            pass
        return extra

    def report_info(self, kind):
        return report.info(kind, state.get_wow_path(), self._report_extra())

    def recent_captures(self):
        try:
            return {"items": report.recent_captures(state.get_wow_path())}
        except Exception as e:
            log("captures recentes illisibles : %r" % e)
            return {"items": []}

    def thumbnail(self, path):
        try:
            return {"data_url": report.thumbnail(path)}
        except Exception:
            return {"data_url": None}

    def pick_attachments(self):
        import webview
        try:
            res = self._window.create_file_dialog(webview.FileDialog.OPEN, allow_multiple=True,
                                                  file_types=_ATTACH_FILTER)
        except Exception as e:
            log("selecteur de fichiers : %r" % e)
            res = None
        return {"paths": list(res or [])}

    def send_report(self, kind, text, attachments, include_log):
        """Envoi en arriere-plan : onReportProgress(pct, msg) puis onReportDone(ok, numero, msg)."""
        err = report.precheck(kind, text, attachments)
        if err:
            return {"started": False, "error": err}
        if not self._report_busy.acquire(blocking=False):
            return {"started": False, "error": "Un envoi est déjà en cours."}
        wow_path, extra = state.get_wow_path(), self._report_extra()

        def worker():
            try:
                progress = _throttled(lambda p, m: self._emit("onReportProgress", p, m), 0.25)
                r = report.send(kind, text, attachments, bool(include_log), wow_path, extra,
                                progress=progress)
            except Exception as e:
                log("signalement : echec (%s)" % type(e).__name__)
                r = {"ok": False, "number": None, "error": "Envoi impossible. Réessaie plus tard."}
            finally:
                self._report_busy.release()
            self._emit("onReportDone", bool(r.get("ok")), r.get("number"),
                       r.get("message") or r.get("error") or "")

        threading.Thread(target=worker, daemon=True).start()
        return {"started": True}

    def open_log(self):
        try:
            subprocess.Popen(["notepad.exe", report._log_file()],
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ------------------------------------------------------------- divers
    def js_log(self, msg):
        """Ligne de journal envoyee par l'interface (demarrage du pont, erreurs JS)."""
        log("interface : %s" % str(msg)[:300])
        return {"ok": True}

    def launch_game(self):
        """Lance l'executable du jeu depuis le dossier d'install."""
        wow_path = state.get_wow_path()
        exe = wow.find_exe(wow_path)
        if not exe:
            return {"ok": False, "error": "Wow.exe introuvable dans le dossier."}
        try:
            subprocess.Popen([exe], cwd=wow_path)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def has_game_exe(self):
        return {"present": bool(wow.find_exe(state.get_wow_path()))}

    def open_addons_folder(self):
        wow_path = state.get_wow_path()
        if not wow.is_valid_install(wow_path):
            return {"ok": False, "error": "Dossier WoW invalide."}
        folder = wow.addons_dir(wow_path)
        os.makedirs(folder, exist_ok=True)
        try:
            os.startfile(folder)  # Windows
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def open_url(self, url):
        # Jamais un chemin local ni un programme : seulement une page web des sites connus.
        if not _url_ok(url):
            return {"ok": False, "error": "Lien refusé."}
        webbrowser.open(url)
        return {"ok": True}

    # ------------------------------------------------------------ helpers
    def _find(self, product_id):
        if not self._manifest:
            self._manifest, self._source = catalog.fetch_offline()
        for p in catalog.products(self._manifest):
            if p["id"] == product_id:
                return p
        return None

    def _emit(self, fn, *args):
        if self._window is None:
            return
        payload = ", ".join(json.dumps(a) for a in args)
        self._window.evaluate_js("window.%s && window.%s(%s)" % (fn, fn, payload))
