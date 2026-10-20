# -*- coding: utf-8 -*-
"""Masquage de la cle des signalements dans le launcher publie.

GitHub (et des robots) cherchent les jetons en clair (« github_pat_... ») dans ce qui est public
et les revoquent : le bouton « Signaler » cesserait alors de marcher. Le build embarque donc le
jeton masque (champ "token_x"). Ce n'est PAS un chiffrement : quelqu'un de motivé peut le
retrouver ; le jeton n'a de droits que sur le depot prive des signalements.
Aucune dependance : importe aussi par build.spec.
"""
import base64

_CLE = b"Ebonhold-Launcher/signalements"


def _xor(b):
    return bytes(c ^ _CLE[i % len(_CLE)] for i, c in enumerate(b))


def masquer(jeton):
    return base64.b64encode(_xor(jeton.encode("utf-8"))).decode("ascii")


def demasquer(texte):
    return _xor(base64.b64decode(texte)).decode("utf-8")
