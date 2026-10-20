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
    if not sha256:
        raise ValueError("Mise a jour sans empreinte SHA256 : refusee par securite.")

    tmp = tempfile.mkdtemp(prefix="ebonhold-upd-")
    zip_path = os.path.join(tmp, "update.zip")
    actual = installer.download(download_url, zip_path, progress)
    if actual.lower() != sha256.lower():
        raise ValueError("Checksum du launcher invalide — mise a jour abandonnee.")

    progress(100, "Extraction...")
    extract_dir = os.path.join(tmp, "x")
    os.makedirs(extract_dir)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(extract_dir)

    new_dir = _find_app_dir(extract_dir, exe_name)
    if not new_dir:
        raise RuntimeError("EbonholdLauncher.exe introuvable dans la mise à jour.")

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
    """Lance un .bat detache : attend la fermeture, remplace les fichiers du launcher, relance.

    Seul le dossier _internal (qui n'appartient qu'au launcher) est mis en miroir. A la
    racine, les fichiers de la nouvelle version sont copies SANS rien supprimer : si le
    launcher a ete pose sur le Bureau ou dans Telechargements, les autres fichiers de ce
    dossier ne sont jamais touches (l'ancienne version faisait un miroir de tout le dossier)."""
    bat = os.path.join(tempfile.gettempdir(), "ebonhold_update.bat")
    with open(bat, "w", encoding="utf-8", newline="\r\n") as f:
        f.write(swapper_script(cur_dir, new_dir, exe_name, tmp_dir))
    subprocess.Popen(["cmd", "/c", bat],
                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def swapper_script(cur_dir, new_dir, exe_name, tmp_dir):
    """Texte du .bat de remplacement (separe pour pouvoir le verifier sans l'executer)."""
    target_exe = os.path.join(cur_dir, exe_name)
    new_internal = os.path.join(new_dir, "_internal")
    cur_internal = os.path.join(cur_dir, "_internal")
    lines = [
        "@echo off",
        "chcp 65001 >nul",                                      # chemins avec accents
        "ping 127.0.0.1 -n 3 >nul",                             # laisse le launcher se fermer
        ":wait",
        'tasklist /fi "imagename eq %s" | find /i "%s" >nul && (' % (exe_name, exe_name),
        "  ping 127.0.0.1 -n 2 >nul",
        "  goto wait",
        ")",
    ]
    if os.path.isdir(new_internal):
        lines.append('robocopy "%s" "%s" /MIR /R:3 /W:1 >nul' % (new_internal, cur_internal))
    lines += [
        'robocopy "%s" "%s" /R:3 /W:1 >nul' % (new_dir, cur_dir),  # racine : copie, sans suppression
        'start "" "%s"' % target_exe,                           # relance
        'rmdir /s /q "%s"' % tmp_dir,                           # nettoie le temp
        'del "%~f0"',                                           # auto-suppression du .bat
    ]
    return "\n".join(lines) + "\n"
