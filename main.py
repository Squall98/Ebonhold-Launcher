# -*- coding: utf-8 -*-
"""Point d'entree du launcher Ebonhold.

Cree la fenetre pywebview qui charge web/index.html et expose l'API Python.
Lancer en dev :  python launcher/main.py
"""
import os

import webview

from core.api import Api
from core.paths import data_dir, resource, startup_log

WINDOW_TITLE = "Ebonhold Launcher"


def main():
    # Repart d'un journal de demarrage propre a chaque lancement (diagnostic).
    try:
        os.remove(os.path.join(data_dir(), "startup.log"))
    except OSError:
        pass
    startup_log("=== main() ===")

    # WebView2 (moteur Edge embarque) peut attendre plusieurs minutes au demarrage s'il
    # tente de joindre un proxy systeme ou ses services reseau. On le force en direct +
    # on coupe son trafic de fond -> demarrage immediat meme derriere un proxy/pare-feu.
    os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = (
        "--no-proxy-server "
        "--disable-background-networking "
        "--disable-component-update"
    )
    api = Api()
    startup_log("avant create_window")
    window = webview.create_window(
        WINDOW_TITLE,
        url=resource("web/index.html"),
        js_api=api,
        width=1000,
        height=700,
        min_size=(820, 560),
        background_color="#0f1320",
    )
    api.window = window
    startup_log("avant webview.start()")
    # http_server=True : sert l'UI via un petit serveur local au lieu de file:// ->
    #   le pont js<->python (window.pywebview.api) s'initialise plus vite et plus surement.
    # private_mode=False + storage_path : WebView2 reutilise son profil entre les
    #   lancements (au lieu d'en recreer un temporaire) -> demarrages suivants plus rapides.
    webview.start(http_server=True, private_mode=False,
                  storage_path=os.path.join(data_dir(), "webview"))


if __name__ == "__main__":
    main()
