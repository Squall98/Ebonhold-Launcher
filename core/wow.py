# -*- coding: utf-8 -*-
"""Detection et chemins de l'installation WoW / Ebonhold du joueur.

Reprend la logique de detection de l'installeur FR existant
(github/EbonholdFR-Client/installer/ebonhold_fr_installer.py:find_ebonhold).
"""
import os

# Marqueurs prouvant qu'un dossier est bien une install Ebonhold (3.3.5a).
_DATA_MARKERS = ("patch-5.MPQ", "common.MPQ", "lichking.MPQ")


def is_valid_install(install_dir):
    """True si install_dir contient un dossier Data avec au moins un patch reconnu."""
    if not install_dir:
        return False
    data = os.path.join(install_dir, "Data")
    if not os.path.isdir(data):
        return False
    return any(os.path.exists(os.path.join(data, m)) for m in _DATA_MARKERS)


def autodetect():
    """Cherche une install Ebonhold sur les emplacements classiques. Renvoie '' si rien."""
    for drive in "CDEFGH":
        for sub in (r"\ebonhold\Ebonhold", r"\Ebonhold", r"\Games\Ebonhold",
                    r"\Program Files\Ebonhold", r"\Program Files (x86)\Ebonhold"):
            p = drive + ":" + sub
            if is_valid_install(p):
                return p
    return ""


def addons_dir(install_dir):
    """Dossier Interface\\AddOns (cree au besoin par l'appelant)."""
    return os.path.join(install_dir, "Interface", "AddOns")


def data_dir(install_dir):
    """Dossier Data (patches MPQ)."""
    return os.path.join(install_dir, "Data")


def find_exe(install_dir):
    """Renvoie le chemin de l'executable du jeu (Wow.exe / Ebonhold.exe) ou '' si absent."""
    for name in ("Wow.exe", "WoW.exe", "Ebonhold.exe", "Project-Epoch.exe"):
        p = os.path.join(install_dir, name)
        if os.path.exists(p):
            return p
    return ""


def target_dir(install_dir, install_target):
    """Resout la destination d'un produit selon son champ manifest 'install_target'."""
    if install_target == "addons":
        return addons_dir(install_dir)
    if install_target == "data":
        return data_dir(install_dir)
    raise ValueError("install_target inconnu: %r" % install_target)
