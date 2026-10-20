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
import re
import shutil
import stat
import sys

from . import paths, wow

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
    """Importe le lecteur MPQ + outils embarques. Renvoie (lecteur, mpqwrite, dbc_localize)
    ou leve. Le lecteur (vendor/mpqread, base sur mpyq) lit aussi les fichiers chiffres et
    les compressions que mpyq seul refuse."""
    import mpyq          # pip  # noqa: F401  (requis par mpqread)
    import mpqread       # vendor/
    import mpqwrite      # vendor/
    import dbc_localize  # vendor/
    return mpqread, mpqwrite, dbc_localize


def _open(mpqread, path, listfile=False):
    return mpqread.Archive(path, listfile=listfile)


def _read(arc, inner):
    try:
        return arc.read(inner)
    except Exception:
        return arc.read_file(inner)


def _patch_priority(name):
    """Rang de chargement d'un patch du dossier Data : patch.MPQ, puis patch-2..9, puis
    patch-A..Z. Plus le rang est haut, plus le fichier l'emporte. None si ce n'est pas un patch."""
    m = re.match(r"^patch(?:-([0-9A-Za-z]))?\.mpq$", name, re.I)
    if not m:
        return None
    c = m.group(1)
    if c is None:
        return 0
    return int(c) if c.isdigit() else 10 + ord(c.upper()) - ord("A")


def _patches_by_priority(data_dir):
    """Patchs du serveur, du plus prioritaire au moins prioritaire. patch-Z (le notre) exclu."""
    out = []
    for n in os.listdir(data_dir):
        p = _patch_priority(n)
        if p is not None and n.upper() != "PATCH-Z.MPQ":
            out.append((p, n))
    return [n for _, n in sorted(out, reverse=True)]


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
    with open(_STORE, encoding="utf-8") as f:
        s = json.load(f)
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


_PROF_NAMES = {
    "PROFESSION_FIRST_AID": "Secourisme", "PROFESSION_COOKING": "Cuisine",
    "PROFESSION_FISHING": "Pêche", "TRADESKILL_ALCHEMY": "Alchimie",
    "TRADESKILL_BLACKSMITHING": "Forge", "TRADESKILL_ENCHANTING": "Enchantement",
    "TRADESKILL_ENGINEERING": "Ingénierie", "TRADESKILL_HERBALISM": "Herboristerie",
    "TRADESKILL_INSCRIPTION": "Calligraphie", "TRADESKILL_JEWELCRAFTING": "Joaillerie",
    "TRADESKILL_LEATHERWORKING": "Travail du cuir", "TRADESKILL_MINING": "Minage",
    "TRADESKILL_SKINNING": "Dépeçage", "TRADESKILL_TAILORING": "Couture",
}
_SBF_GUARDS = [
    '_frame.button1:SetAttribute("spell", v.downSpell)',
    '_frame.button2:SetAttribute("spell", v.upSpell)',
    '_frame.button1:SetAttribute("spell", c.downSpell)',
    '_frame.button2:SetAttribute("spell", c["Up"])',
]
_TDB_REPL = {
    'computedDesc = "Increases your Stamina by %s."':
        'computedDesc = "Augmente votre Endurance de %s."',
    'computedDesc = "Increases your Strength, Agility, Intellect or Spirit by %s, whichever is highest."':
        'computedDesc = "Augmente votre Force, Agilité, Intelligence ou Esprit de %s (la plus élevée)."',
    'computedDesc = "Increases your attack power by %s or your spell power by %s, whichever is higher."':
        'computedDesc = "Augmente votre puissance d\'attaque de %s ou votre puissance des sorts de %s (la plus élevée)."',
    'name = "Default Soul Tree"': 'name = "Arbre d\'âmes par défaut"',
    'description = "Universal soul tree for all classes"':
        'description = "Arbre d\'âmes universel pour toutes les classes"',
}


_ARCHIVES = {}


def _close_archives():
    """Relache les fichiers du jeu (sinon l'updater officiel ne pourrait plus les remplacer)."""
    for arc in _ARCHIVES.values():
        try:
            arc.file.close()
        except Exception:
            pass
    _ARCHIVES.clear()


def _cached(mpqread, path):
    """Archive ouverte une seule fois par construction (les gros patchs HD font plusieurs Go)."""
    key = (path, os.path.getmtime(path))
    if key not in _ARCHIVES:
        try:
            _ARCHIVES[key] = _open(mpqread, path)
        except Exception:
            _ARCHIVES[key] = None
    return _ARCHIVES[key]


def _read_from_patches(mpqread, data_dir, inner, patches):
    """Lit `inner` dans le premier patch qui le contient (liste du plus prioritaire au moins
    prioritaire) : c'est la version que le jeu utilise vraiment."""
    for rel in patches:
        p = os.path.join(data_dir, rel)
        if not os.path.exists(p):
            continue
        try:
            arc = _cached(mpqread, p)
            d = _read(arc, inner) if arc is not None else None
            if d:
                return d
        except Exception:
            pass
    return None


def _add_addon_fixes(mpqread, data_dir, patchz, log):
    order = _patches_by_priority(data_dir)
    SBF = r"Interface\FrameXML\SpellBookFrame.lua"
    d = _read_from_patches(mpqread, data_dir, SBF, order)
    if d:
        body = d.decode("utf-8", "replace")
        prefix = "-- [EbonholdFR] noms de metiers FR + anti-taint\n"
        for c, name in _PROF_NAMES.items():
            prefix += 'if not %s then %s = "%s" end\n' % (c, c, name)
        body = prefix + "\n" + body
        for g in _SBF_GUARDS:
            if body.count(g) == 1:
                body = body.replace(g, "if issecure() then " + g + " end")
        patchz[SBF] = body.encode("utf-8")
        log("Fix metiers (SpellBookFrame) ajoute a patch-Z.")
    TDB = r"Interface\AddOns\ProjectEbonhold\modules\skillTree\TalentDatabase.lua"
    d = _read_from_patches(mpqread, data_dir, TDB, order)
    if d:
        body = d.decode("utf-8", "replace")
        n = 0
        for en, fr in _TDB_REPL.items():
            if body.count(en) == 1:
                body = body.replace(en, fr); n += 1
        if n:
            patchz[TDB] = body.encode("utf-8")
            log("Fix skill tree (TalentDatabase) ajoute a patch-Z.")


def _build_patchz(data_dir, base_fr, spells_fr, other_fr, log):
    mpqread, mpqwrite, dbc_localize = _deps()
    fr_col = 2 if base_fr else 0
    tr = _load_tr()
    want = {"spells": spells_fr, "other": other_fr}
    fr_arch = []
    if base_fr:
        for m in FR_MPQS:
            p = os.path.join(data_dir, "frFR", m)
            if os.path.exists(p):
                try:
                    fr_arch.append(_open(mpqread, p))
                except Exception:
                    pass

    def find_base(path):
        for a in fr_arch:
            try:
                d = _read(a, path)
                if d:
                    return d
            except Exception:
                pass
        return None

    # Un DBC peut exister dans plusieurs patchs : on prend toujours la version du patch le
    # plus prioritaire (celle que le jeu charge), jamais une copie plus ancienne. Seuls les
    # patchs qui passent DEVANT patch-5/6 comptent (patch.MPQ, patch-2/3 sont plus anciens).
    floor = min(_patch_priority(p) for p in TEXT_PATCHES)
    order = [n for n in _patches_by_priority(data_dir) if _patch_priority(n) >= floor]
    _close_archives()
    try:
        patchz = _collect_patchz(data_dir, mpqread, dbc_localize, tr, want, base_fr, fr_col,
                                 find_base, order, log)
    finally:
        _close_archives()
        for a in fr_arch:
            try:
                a.file.close()
            except Exception:
                pass
    if patchz:
        mpqwrite.create_mpq(os.path.join(data_dir, "patch-Z.MPQ"), patchz)
        log("patch-Z.MPQ ecrit (%d fichiers)." % len(patchz))
    else:
        _remove_patchz(data_dir)
        log("patch-Z retire (rien a traduire).")


def _collect_patchz(data_dir, mpqread, dbc_localize, tr, want, base_fr, fr_col, find_base, order, log):
    patchz = {}
    seen = set()
    for patch in TEXT_PATCHES:
        sp = os.path.join(data_dir, patch)
        if not os.path.exists(sp):
            continue
        a = _cached(mpqread, sp)
        if a is None:
            continue
        names = [n for n in _read(a, "(listfile)").decode("latin-1")
                 .replace("\r\n", "\n").split("\n") if n.strip()]
        for n in names:
            if not n.lower().endswith(".dbc") or n.lower() in seen:
                continue
            seen.add(n.lower())
            g_fr = want[_group_of(n)]
            if not base_fr and not g_fr:
                continue
            raw = _read_from_patches(mpqread, data_dir, n, order) or _read(a, n)
            use_base = base_fr and g_fr
            use_tr = tr if g_fr else {}
            base = find_base(n) if use_base else None
            try:
                merged, _ = dbc_localize.merge(raw, base, use_tr, fr_col=fr_col)
            except Exception:
                merged = None
            if merged:
                patchz[n] = merged
    if base_fr:                       # fixes interface custom (metiers, skill tree)
        try:
            _add_addon_fixes(mpqread, data_dir, patchz, log)
        except Exception as e:
            log("Fixes interface non ajoutes (%s)." % e)
    return patchz


def apply(install_dir, base_fr, voices_fr, spells_fr, other_fr, log):
    """Applique la config langue. `log` = callable(str) pour le journal en direct."""
    ok, err = is_available()
    if not ok:
        raise RuntimeError(err)
    if wow.game_running():
        raise RuntimeError("Ferme d'abord le jeu (Wow.exe) : ses fichiers ne peuvent pas etre "
                           "modifies pendant qu'il tourne.")
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
