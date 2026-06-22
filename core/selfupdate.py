# -*- coding: utf-8 -*-
"""Auto-update du launcher lui-meme.

Cas 'exe' (PyInstaller, sys.frozen) : telecharge le nouveau .exe, verifie son SHA256,
puis lance un petit script .bat qui attend la fermeture du launcher, remplace l'.exe et
le relance. Un programme ne pouvant pas se reecrire pendant qu'il tourne, on passe par
ce relais — c'est la methode standard.

Cas 'dev' (lance via python) : pas de .exe a remplacer, on se contente d'ouvrir la page
de telechargement (gere par l'appelant). is_frozen() permet de distinguer les deux.
"""
import os
import subprocess
import sys
import tempfile

from . import installer  # reutilise download() + verification SHA256


def is_frozen():
    """True si on tourne en .exe PyInstaller (et non via l'interpreteur Python)."""
    return bool(getattr(sys, "frozen", False))


def exe_path():
    return sys.executable if is_frozen() else ""


def download_and_swap(download_url, sha256, progress=None):
    """Telecharge le nouvel .exe, le verifie, puis declenche le remplacement + relance.

    A appeler seulement si is_frozen(). Le launcher doit ensuite QUITTER pour liberer
    son .exe (l'appelant ferme la fenetre apres le retour).
    """
    if not is_frozen():
        raise RuntimeError("Remplacement auto disponible uniquement sur la version .exe.")

    progress = progress or (lambda *_: None)
    current = exe_path()
    new_exe = os.path.join(tempfile.gettempdir(), "EbonholdLauncher.new.exe")

    actual = installer.download(download_url, new_exe, progress)
    if sha256 and actual.lower() != sha256.lower():
        os.remove(new_exe)
        raise ValueError("Checksum du launcher invalide — telechargement abandonne.")

    _spawn_swapper(current, new_exe)
    return True


def _spawn_swapper(current_exe, new_exe):
    """Cree et lance un .bat detache qui attend, remplace l'.exe et relance."""
    bat = os.path.join(tempfile.gettempdir(), "ebonhold_update.bat")
    script = (
        "@echo off\r\n"
        "ping 127.0.0.1 -n 3 >nul\r\n"                 # laisse le launcher se fermer
        ':wait\r\n'
        'tasklist /fi "imagename eq %s" | find /i "%s" >nul && (\r\n'
        "  ping 127.0.0.1 -n 2 >nul\r\n"
        "  goto wait\r\n"
        ")\r\n"
        'move /y "%s" "%s" >nul\r\n'                   # remplace l'ancien par le nouveau
        'start "" "%s"\r\n'                            # relance
        'del "%%~f0"\r\n'                              # auto-suppression du .bat
    ) % (
        os.path.basename(current_exe), os.path.basename(current_exe),
        new_exe, current_exe, current_exe,
    )
    with open(bat, "w", encoding="ascii") as f:
        f.write(script)
    subprocess.Popen(["cmd", "/c", bat],
                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
