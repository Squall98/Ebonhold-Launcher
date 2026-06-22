# -*- coding: utf-8 -*-
"""API Python exposee au frontend JS via pywebview (window.pywebview.api.*).

Toutes les operations longues (install/maj) tournent dans un thread et poussent
leur progression au JS via window.evaluate_js(onProgress / onDone).
"""
import json
import os
import subprocess
import threading
import webbrowser

from . import catalog, frconfig, frpack, installer, selfupdate, state, version, wow


def _status(product, installed_version):
    if installed_version is None:
        return "install"
    if installed_version == product["version"]:
        return "uptodate"
    return "update"


class Api:
    def __init__(self):
        self._window = None          # injecte par main.py ; prefixe _ OBLIGATOIRE :
        # pywebview introspecte tout attribut PUBLIC non-callable du js_api au boot et
        # recurse dans l'objet fenetre WebView2 natif (-> "maximum recursion depth" +
        # blocage de plusieurs minutes). Les noms en _ sont ignores par get_functions().
        self._manifest = None
        self._source = None

    # ----------------------------------------------------------- catalogue
    def get_catalog(self, check_remote=False):
        """Retourne l'etat complet pour l'UI, INSTANTANEMENT (manifeste local embarque).

        Aucun appel reseau sur ce chemin -> demarrage immediat, pas de "Ne repond pas".
        Si check_remote=True, on verifie le catalogue en ligne EN ARRIERE-PLAN (thread)
        et on pousse la mise a jour au JS via onCatalogUpdate quand elle est prete.
        """
        self._manifest, self._source = catalog.fetch(prefer_remote=False)
        resp = self._build_catalog()
        if check_remote:
            threading.Thread(target=self._remote_refresh, daemon=True).start()
        return resp

    def _remote_refresh(self):
        """Recupere le manifeste en ligne en fond ; pousse onCatalogUpdate si dispo."""
        try:
            man = catalog._load_remote()
        except Exception:
            return  # hors-ligne ou repo injoignable -> on garde le local, sans bloquer
        self._manifest, self._source = man, "remote"
        self._emit("onCatalogUpdate", self._build_catalog())

    def _build_catalog(self):
        """Construit la reponse catalogue a partir de self._manifest (sans reseau)."""
        wow_path = state.get_wow_path() or wow.autodetect()
        if wow_path and not state.get_wow_path():
            state.set_wow_path(wow_path)

        wow_valid = wow.is_valid_install(wow_path)
        items = []
        updates = 0
        by_id = {}
        for p in catalog.products(self._manifest):
            entry = state.get_installed(p["id"])
            installed_version = entry["version"] if entry else None
            st = _status(p, installed_version)
            # Un mod installe dont des fichiers ont disparu -> a reparer.
            if installed_version is not None and wow_valid and installer.is_broken(p["id"], wow_path):
                st = "repair"
            if st != "uptodate":
                updates += 1
            row = {
                "id": p["id"],
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
        result = self._window.create_file_dialog(webview.FOLDER_DIALOG)
        if not result:
            return {"ok": False, "path": state.get_wow_path()}
        path = result[0]
        if not wow.is_valid_install(path):
            return {"ok": False, "path": path,
                    "error": "Ce dossier n'est pas une install Ebonhold (Data\\ introuvable)."}
        state.set_wow_path(path)
        return {"ok": True, "path": path}

    # ----------------------------------------------------- install / update
    def install_product(self, product_id):
        """Lance l'installation/maj en arriere-plan. La progression arrive via onProgress/onDone."""
        product = self._find(product_id)
        if product is None:
            return {"started": False, "error": "Produit inconnu."}
        wow_path = state.get_wow_path()
        if not wow.is_valid_install(wow_path):
            return {"started": False, "error": "Choisis d'abord ton dossier Ebonhold."}

        def worker():
            def progress(pct, msg):
                self._emit("onProgress", product_id, pct, msg)
            try:
                installer.install(product, wow_path, progress)
                self._emit("onDone", product_id, True, "Installe (v%s)." % product["version"])
            except Exception as e:
                self._emit("onDone", product_id, False, str(e))

        threading.Thread(target=worker, daemon=True).start()
        return {"started": True}

    def uninstall_product(self, product_id):
        wow_path = state.get_wow_path()
        try:
            installer.uninstall(product_id, wow_path)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def install_all(self):
        """Installe/MAJ tous les produits qui ne sont pas deja a jour (un par un)."""
        if not self._manifest:
            self.get_catalog()
        ids = []
        for p in catalog.products(self._manifest):
            entry = state.get_installed(p["id"])
            iv = entry["version"] if entry else None
            if _status(p, iv) != "uptodate":
                ids.append(p["id"])
        for pid in ids:
            self.install_product(pid)
        return {"started": True, "count": len(ids)}

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

        def worker():
            def progress(pct, msg):
                self._emit("onLauncherProgress", pct, msg)
            try:
                selfupdate.download_and_swap(url, sha, progress)
                self._emit("onLauncherReady")          # le JS demande la fermeture
                if self._window is not None:
                    self._window.destroy()                # quitte pour liberer l'.exe
            except Exception as e:
                self._emit("onLauncherError", str(e))

        threading.Thread(target=worker, daemon=True).start()
        return {"ok": True, "mode": "exe"}

    # ------------------------------------------------------- config langue FR
    def get_fr_status(self):
        ok, err = frconfig.is_available()
        wow_path = state.get_wow_path()
        if not self._manifest:
            self._manifest, self._source = catalog.fetch(prefer_remote=False)
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
            self._manifest, self._source = catalog.fetch(prefer_remote=False)
        spec = (self._manifest.get("fr_config", {}) or {}).get("pack_download") or {}
        if not (spec.get("url") or spec.get("parts")):
            return {"started": False, "error": "Aucune source de pack configuree."}

        def worker():
            def progress(pct, msg):
                self._emit("onPackProgress", pct, msg)
            def log(msg):
                self._emit("onFrLog", msg)
            try:
                frpack.install(wow_path, spec, progress, log)
                self._emit("onPackDone", True, "Pack frFR installe.")
            except Exception as e:
                self._emit("onPackDone", False, str(e))

        threading.Thread(target=worker, daemon=True).start()
        return {"started": True}

    def apply_fr_config(self, base_fr, voices_fr, spells_fr, other_fr):
        """Applique la config langue en arriere-plan. Journal via onFrLog, fin via onFrDone."""
        wow_path = state.get_wow_path()
        if not wow.is_valid_install(wow_path):
            return {"started": False, "error": "Choisis d'abord ton dossier Ebonhold."}

        def worker():
            def log(msg):
                self._emit("onFrLog", msg)
            try:
                frconfig.apply(wow_path, base_fr, voices_fr, spells_fr, other_fr, log)
                self._emit("onFrDone", True, "Configuration appliquee. Lance le jeu.")
            except Exception as e:
                self._emit("onFrDone", False, str(e))

        threading.Thread(target=worker, daemon=True).start()
        return {"started": True}

    # ------------------------------------------------------------- divers
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
        webbrowser.open(url)
        return {"ok": True}

    # ------------------------------------------------------------ helpers
    def _find(self, product_id):
        if not self._manifest:
            self._manifest, self._source = catalog.fetch(prefer_remote=False)
        for p in catalog.products(self._manifest):
            if p["id"] == product_id:
                return p
        return None

    def _emit(self, fn, *args):
        if self._window is None:
            return
        payload = ", ".join(json.dumps(a) for a in args)
        self._window.evaluate_js("window.%s && window.%s(%s)" % (fn, fn, payload))
