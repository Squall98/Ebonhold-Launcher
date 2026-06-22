# -*- coding: utf-8 -*-
"""Configuration langue FR — version autonome.

Reprend la logique de l'installeur EbonholdFR-Client mais en s'appuyant uniquement
sur les outils/donnees embarques dans `launcher/vendor/` (mpqwrite, dbc_localize,
custom_translations.json, addon EbonholdFRFix) + le module pip `mpyq`. Plus aucune
dependance vers un dossier externe -> packageable tel quel.

Methode NON-DESTRUCTIVE : le francais est injecte dans un patch SEPARE 'patch-Z.MPQ'
qui surcharge patch-5/6 sans les modifier.
"""
import json
import os
import shutil
import stat
import sys

from . import paths

_VENDOR = paths.resource("vendor")
if _VENDOR not in sys.path:
    sys.path.insert(0, _VENDOR)

FR_MPQS = ["patch-frFR-3.MPQ", "patch-frFR-2.MPQ", "patch-frFR.MPQ", "locale-frFR.MPQ"]
TEXT_PATCHES = ["patch-5.MPQ", "patch-6.MPQ"]
SPEECH = [
    ("speech-frFR.MPQ", "speech-enUS.MPQ"),
    ("lichking-speech-frFR.MPQ", "lichking-speech-enUS.MPQ"),
    ("expansion-speech-frFR.MPQ", "expansion-speech-enUS.MPQ"),
]
_STORE = os.path.join(_VENDOR, "custom_translations.json")
_ADDON_SRC = os.path.join(_VENDOR, "EbonholdFRFix")

_load_error = None


def _deps():
    """Importe mpyq + outils embarques. Renvoie (mpyq, mpqwrite, dbc_localize) ou leve."""
    import mpyq          # pip
    import mpqwrite      # vendor/
    import dbc_localize  # vendor/
    return mpyq, mpqwrite, dbc_localize


def is_available():
    global _load_error
    if not os.path.isfile(_STORE):
        _load_error = "Donnees FR manquantes (vendor/custom_translations.json)."
        return False, _load_error
    try:
        _deps()
    except Exception as e:
        _load_error = "Dependance FR manquante : %s (installe 'mpyq')." % e
        return False, _load_error
    return True, ""


# ------------------------------------------------------------------ helpers FR

def _load_tr():
    s = json.load(open(_STORE, encoding="utf-8"))
    tr = {}
    tr.update(s.get("names", {}))
    tr.update(s.get("descs", {}))
    return tr


def has_pack(data_dir):
    """Pack frFR (~2,4 Go) present ? Requis pour mettre le JEU en francais."""
    return os.path.exists(os.path.join(data_dir, "frFR", "locale-frFR.MPQ"))


def pack_present(install_dir):
    return has_pack(os.path.join(install_dir, "Data")) if install_dir else False


def _make_writable(path):
    """Enleve l'attribut lecture seule (Config.wtf/realmlist.wtf sont souvent en read-only
    sur les serveurs prives pour figer le realmlist)."""
    if os.path.exists(path):
        try:
            os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
        except OSError:
            pass


def _set_locale(install_dir, locale):
    cfg = os.path.join(install_dir, "WTF", "Config.wtf")
    lines = open(cfg, encoding="latin-1").read().splitlines() if os.path.exists(cfg) else []
    out, found = [], False
    for ln in lines:
        if ln.strip().upper().startswith("SET LOCALE"):
            out.append('SET locale "%s"' % locale); found = True
        else:
            out.append(ln)
    if not found:
        out.insert(0, 'SET locale "%s"' % locale)
    os.makedirs(os.path.dirname(cfg), exist_ok=True)
    _make_writable(cfg)
    try:
        open(cfg, "w", encoding="latin-1").write("\n".join(out) + "\n")
    except PermissionError:
        raise RuntimeError(
            "Impossible d'ecrire Config.wtf (acces refuse). Ferme COMPLETEMENT le jeu "
            "et le launcher officiel Ebonhold, puis reessaie. Si le fichier est en lecture "
            "seule, le launcher l'a normalement deverrouille — reessaie une fois.")


def _fix_realmlist(data_dir):
    en = os.path.join(data_dir, "enUS", "realmlist.wtf")
    fr = os.path.join(data_dir, "frFR", "realmlist.wtf")
    if os.path.exists(en) and os.path.isdir(os.path.dirname(fr)):
        _make_writable(fr)
        try:
            shutil.copy2(en, fr)
        except (PermissionError, OSError):
            pass  # realmlist FR non critique pour la traduction


def _remove_patchz(data_dir):
    p = os.path.join(data_dir, "patch-Z.MPQ")
    if os.path.exists(p):
        os.remove(p)


def _deploy_addon(install_dir, log):
    """Installe l'addon compagnon EbonholdFRFix (reactive les interfaces custom en FR)."""
    if not os.path.isdir(_ADDON_SRC):
        return
    dst = os.path.join(install_dir, "Interface", "AddOns", "EbonholdFRFix")
    try:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.isdir(dst):
            shutil.rmtree(dst, ignore_errors=True)
        shutil.copytree(_ADDON_SRC, dst)
        log("Addon EbonholdFRFix installe (forge custom OK en francais).")
    except Exception as e:
        log("Addon non installe (%s)." % e)


def _manage_voices(data_dir, voices_fr, log):
    frdir = os.path.join(data_dir, "frFR")
    endir = os.path.join(data_dir, "enUS")
    for frname, enname in SPEECH:
        frp = os.path.join(frdir, frname)
        bak = frp + ".fr-backup"
        enp = os.path.join(endir, enname)
        if voices_fr:
            if os.path.exists(bak):
                if os.path.exists(frp):
                    os.remove(frp)
                os.rename(bak, frp)
                log("Voix FR restaurees : %s" % frname)
        else:
            if os.path.exists(enp):
                if os.path.exists(frp) and not os.path.exists(bak):
                    os.rename(frp, bak)
                log("Copie voix anglaises -> %s (peut prendre 1 min)..." % frname)
                shutil.copy2(enp, frp)


def _group_of(dbc_name):
    return "spells" if dbc_name.lower().endswith("spell.dbc") else "other"


def _build_patchz(data_dir, base_fr, spells_fr, other_fr, log):
    mpyq, mpqwrite, dbc_localize = _deps()
    fr_col = 2 if base_fr else 0
    tr = _load_tr()
    want = {"spells": spells_fr, "other": other_fr}
    fr_arch = []
    if base_fr:
        for m in FR_MPQS:
            p = os.path.join(data_dir, "frFR", m)
            if os.path.exists(p):
                try:
                    fr_arch.append(mpyq.MPQArchive(p, listfile=False))
                except Exception:
                    pass

    def find_base(path):
        for a in fr_arch:
            try:
                d = a.read_file(path)
                if d:
                    return d
            except Exception:
                pass
        return None

    patchz = {}
    for patch in TEXT_PATCHES:
        sp = os.path.join(data_dir, patch)
        if not os.path.exists(sp):
            continue
        a = mpyq.MPQArchive(sp)
        names = [n for n in a.read_file("(listfile)").decode("latin-1")
                 .replace("\r\n", "\n").split("\n") if n.strip()]
        for n in names:
            if not n.lower().endswith(".dbc"):
                continue
            g_fr = want[_group_of(n)]
            if not base_fr and not g_fr:
                continue
            raw = a.read_file(n)
            use_base = base_fr and g_fr
            use_tr = tr if g_fr else {}
            base = find_base(n) if use_base else None
            try:
                merged, _ = dbc_localize.merge(raw, base, use_tr, fr_col=fr_col)
            except Exception:
                merged = None
            if merged:
                patchz[n] = merged
    if patchz:
        mpqwrite.create_mpq(os.path.join(data_dir, "patch-Z.MPQ"), patchz)
        log("patch-Z.MPQ ecrit (%d fichiers)." % len(patchz))
    else:
        _remove_patchz(data_dir)
        log("patch-Z retire (rien a traduire).")


def apply(install_dir, base_fr, voices_fr, spells_fr, other_fr, log):
    """Applique la config langue. `log` = callable(str) pour le journal en direct."""
    ok, err = is_available()
    if not ok:
        raise RuntimeError(err)
    if base_fr and not pack_present(install_dir):
        raise RuntimeError(
            "Le pack frFR (~2,4 Go) est requis pour mettre le jeu en francais. "
            "Installe-le d'abord, ou laisse le Jeu en EN.")
    data = os.path.join(install_dir, "Data")
    if base_fr:
        _fix_realmlist(data)
        _manage_voices(data, voices_fr, log)
    _build_patchz(data, base_fr, spells_fr, other_fr, log)
    _deploy_addon(install_dir, log)
    _set_locale(install_dir, "frFR" if base_fr else "enUS")
    log("Jeu=%s  Voix=%s  Sorts=%s  Reput=%s." % (
        "FR" if base_fr else "EN", "FR" if voices_fr else "EN",
        "FR" if spells_fr else "EN", "FR" if other_fr else "EN"))
