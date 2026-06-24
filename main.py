# -*- coding: utf-8 -*-
"""Point d'entree du launcher Ebonhold.

Cree la fenetre pywebview qui charge web/index.html et expose l'API Python.
Lancer en dev :  python launcher/main.py
"""
import os
import shutil
import sys

import webview

from core.api import Api
from core import version
from core.paths import data_dir, resource

WINDOW_TITLE = "Ebonhold Launcher"


def _unblock_app_files():
    """Retire la marque "fichier venu d'Internet" (flux Zone.Identifier) des fichiers de l'app.

    Quand le launcher est telecharge puis extrait, Windows marque ses fichiers ; .NET refuse
    alors de charger Python.Runtime.dll -> crash au demarrage de la fenetre (clr/pythonnet).
    On retire ces marques nous-memes (uniquement en .exe), AVANT que WebView2/.NET ne charge
    ses DLL, pour que les joueurs n'aient rien a "debloquer" a la main apres telechargement."""
    if not getattr(sys, "frozen", False):
        return
    base = os.path.dirname(sys.executable)
    for root, _dirs, files in os.walk(base):
        for name in files:
            try:
                os.remove(os.path.join(root, name) + ":Zone.Identifier")
            except OSError:
                pass


def _fresh_webview_cache(wv_dir):
    """Vide le cache HTTP de WebView2 quand la version de l'app a change.

    Sinon, apres une mise a jour, WebView2 ressert l'ancien HTML/CSS/JS depuis son cache
    -> l'UI semble ne pas avoir bouge. On ne supprime QUE les dossiers de cache (pas tout le
    profil), pour ne pas declencher une re-init complete de WebView2 (qui ralentit le pont au
    premier lancement). Nettoyage une seule fois par nouvelle version ; le cache se reconstruit."""
    marker = os.path.join(data_dir(), "ui_version.txt")
    last = ""
    try:
        with open(marker, encoding="utf-8") as f:
            last = f.read().strip()
    except OSError:
        pass
    if last == version.APP_VERSION:
        return
    default = os.path.join(wv_dir, "EBWebView", "Default")
    for sub in ("Cache", "Code Cache", "GPUCache"):
        shutil.rmtree(os.path.join(default, sub), ignore_errors=True)
    try:
        os.makedirs(data_dir(), exist_ok=True)
        with open(marker, "w", encoding="utf-8") as f:
            f.write(version.APP_VERSION)
    except OSError:
        pass


def main():
    # AVANT TOUT : debloquer les fichiers de l'app (marque Internet) sinon .NET refuse de
    # charger ses DLL quand le launcher a ete telecharge -> crash. Doit tourner avant webview.start().
    _unblock_app_files()
    # WebView2 (moteur Edge embarque) peut attendre plusieurs minutes au demarrage s'il
    # tente de joindre un proxy systeme ou ses services reseau. On le force en direct +
    # on coupe son trafic de fond -> demarrage immediat meme derriere un proxy/pare-feu.
    os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = (
        "--no-proxy-server "
        "--disable-background-networking "
        "--disable-component-update"
    )
    wv_dir = os.path.join(data_dir(), "webview")
    _fresh_webview_cache(wv_dir)
    api = Api()
    window = webview.create_window(
        WINDOW_TITLE,
        url=resource("web/index.html"),
        js_api=api,
        width=1000,
        height=700,
        min_size=(820, 560),
        background_color="#0f1320",
    )
    api._window = window   # _ obligatoire (voir Api.__init__) sinon pywebview bloque au boot
    # http_server=True est NECESSAIRE : avec file:// le pont js<->python ne s'initialise
    # pas (WebView2 + restrictions file://). Le serveur sert l'UI en local (icones embarquees,
    # aucun acces internet). private_mode=False + storage_path : profil WebView2 reutilise.
    webview.start(http_server=True, private_mode=False, storage_path=wv_dir)


if __name__ == "__main__":
    main()
