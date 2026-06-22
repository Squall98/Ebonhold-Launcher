# -*- coding: utf-8 -*-
"""Point d'entree du launcher Ebonhold.

Cree la fenetre pywebview qui charge web/index.html et expose l'API Python.
Lancer en dev :  python launcher/main.py
"""
import webview

from core.api import Api
from core.paths import resource

WINDOW_TITLE = "Ebonhold Launcher"


def main():
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
    api.window = window
    webview.start()


if __name__ == "__main__":
    main()
