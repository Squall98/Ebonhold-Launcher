# -*- coding: utf-8 -*-
"""Auto-update du launcher lui-meme (format ONE-FOLDER).

Cas 'exe' (PyInstaller, sys.frozen) : le launcher est un dossier
(EbonholdLauncher\\EbonholdLauncher.exe + _internal\\...). On telecharge le nouveau
ZIP, on l'extrait, puis un petit .bat detache attend la fermeture du launcher, remplace
le contenu du dossier (robocopy) et relance. Un programme ne pouvant pas se reecrire
pendant qu'il tourne, ce relais est la methode standard.

Cas 'dev' (lance via python) : rien a remplacer, l'appelant ouvre la page de
telechargement. is_frozen() distingue les deux.
"""
import os
import subprocess
import sys
import tempfile
import zipfile

from . import installer  # reutilise download()


def is_frozen():
    """True si on tourne en .exe PyInstaller (et non via l'interpreteur Python)."""
    return bool(getattr(sys, "frozen", False))


def exe_path():
    return sys.executable if is_frozen() else ""


def app_dir():
    """Dossier du launcher (qui contient EbonholdLauncher.exe + _internal\\)."""
    return os.path.dirname(sys.executable) if is_frozen() else ""


def download_and_swap(download_url, sha256, progress=None):
    """Telecharge le ZIP de la nouvelle version, le verifie, l'extrait, puis declenche
    le remplacement du dossier + la relance. Le launcher doit ensuite QUITTER."""
    if not is_frozen():
        raise RuntimeError("Mise a jour auto disponible uniquement sur la version installee.")

    progress = progress or (lambda *_: None)
    cur_dir = app_dir()
    exe_name = os.path.basename(sys.executable)

    tmp = tempfile.mkdtemp(prefix="ebonhold-upd-")
    zip_path = os.path.join(tmp, "update.zip")
    actual = installer.download(download_url, zip_path, progress)
    if sha256 and actual.lower() != sha256.lower():
        raise ValueError("Checksum du launcher invalide — mise a jour abandonnee.")

    progress(100, "Extraction...")
    extract_dir = os.path.join(tmp, "x")
    os.makedirs(extract_dir)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(extract_dir)

    new_dir = _find_app_dir(extract_dir, exe_name)
    if not new_dir:
        raise RuntimeError("EbonholdLauncher.exe introuvable dans la mise a jour.")

    _spawn_folder_swapper(cur_dir, new_dir, exe_name, tmp)
    return True


def _find_app_dir(root, exe_name):
    """Trouve le dossier (dans l'archive extraite) qui contient l'exe du launcher."""
    if os.path.isfile(os.path.join(root, exe_name)):
        return root
    for cur, _dirs, files in os.walk(root):
        if exe_name in files:
            return cur
    return None


def _spawn_folder_swapper(cur_dir, new_dir, exe_name, tmp_dir):
    """Lance un .bat detache : attend la fermeture, mirroir le nouveau dossier, relance."""
    bat = os.path.join(tempfile.gettempdir(), "ebonhold_update.bat")
    target_exe = os.path.join(cur_dir, exe_name)
    script = (
        "@echo off\r\n"
        "ping 127.0.0.1 -n 3 >nul\r\n"                          # laisse le launcher se fermer
        ":wait\r\n"
        'tasklist /fi "imagename eq %s" | find /i "%s" >nul && (\r\n'
        "  ping 127.0.0.1 -n 2 >nul\r\n"
        "  goto wait\r\n"
        ")\r\n"
        'robocopy "%s" "%s" /MIR /R:3 /W:1 >nul\r\n'            # remplace le contenu du dossier
        'start "" "%s"\r\n'                                     # relance
        'rmdir /s /q "%s"\r\n'                                  # nettoie le temp
        'del "%%~f0"\r\n'                                       # auto-suppression du .bat
    ) % (exe_name, exe_name, new_dir, cur_dir, target_exe, tmp_dir)
    with open(bat, "w", encoding="ascii") as f:
        f.write(script)
    subprocess.Popen(["cmd", "/c", bat],
                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
