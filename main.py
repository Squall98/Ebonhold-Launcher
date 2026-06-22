# -*- coding: utf-8 -*-
"""Point d'entree du launcher Ebonhold.

Cree la fenetre pywebview qui charge web/index.html et expose l'API Python.
Lancer en dev :  python launcher/main.py
"""
import os

import webview

from core.api import Api
from core.paths import data_dir, resource

WINDOW_TITLE = "Ebonhold Launcher"


def main():
    # WebView2 (moteur Edge embarque) peut attendre plusieurs minutes au demarrage s'il
    # tente de joindre un proxy systeme ou ses services reseau. On le force en direct +
    # on coupe son trafic de fond -> demarrage immediat meme derriere un proxy/pare-feu.
    os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = (
        "--no-proxy-server "
        "--disable-background-networking "
        "--disable-component-update"
    )
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
    webview.start(http_server=True, private_mode=False,
                  storage_path=os.path.join(data_dir(), "webview"))


if __name__ == "__main__":
    main()
