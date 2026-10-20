# -*- coding: utf-8 -*-
"""EbonholdFR - ecrans de connexion / choix du royaume / selection et creation de personnage
en francais (PROTOTYPE).

Principe (methode "surcouche gardee", recommandee) : on NE REMPLACE AUCUN fichier du serveur.
patch-Z recoit 4 fichiers :
  Interface\\GlueXML\\GlueLocalization.xml      = fichier Blizzard (jamais modifie par le serveur)
                                                 + 1 ligne <Script file="EbonholdFR_Glue.lua"/>
  Interface\\GlueXML\\EbonholdFR_Glue.lua       = NOUVEAU : textes FR, charge juste apres GlueStrings.lua
                                                 et AVANT tous les ecrans XML. Chaque texte n'est pose
                                                 que si le texte anglais actuel est exactement celui attendu.
  Interface\\GlueXML\\GlueLocalizationPost.lua  = fichier Blizzard (fonction LocalizePost vide)
                                                 + bloc qui traduit, apres chargement, les textes ecrits
                                                 en dur par le serveur (cartes Live/PTR, dialogue PTR...).
Le GlueStrings.lua du serveur (patch-I) reste charge tel quel : une cle ajoutee ou modifiee par le
serveur reste en anglais au lieu de casser quoi que ce soit, meme si patch-Z n'a pas ete reconstruit.

Variante B (--variante-fusion, NON recommandee) : un GlueStrings.lua fusionne qui REMPLACE celui du
serveur (litteraux echanges en place dans le fichier actuel du serveur).

Lecture seule sur le jeu : ce script ne fait que lire les MPQ et ecrit dans --out.
Usage : python glue_fr.py [--data DIR] [--out DIR] [--alias-categories] [--dialogues-dll]
                          [--variante-fusion] [--mpqread DIR_DU_MODULE]
API pour le launcher : construire(data_dir, ouvrir_mpq, log, alias_categories, dialogues_dll)
                       -> (fichiers {nom interne: octets}, rapport dict)
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import struct
import sys
import xml.etree.ElementTree as ET

ICI = os.path.dirname(os.path.abspath(__file__))
GX = "Interface\\GlueXML\\"
FR_MPQS = ["patch-frFR-3.MPQ", "patch-frFR-2.MPQ", "patch-frFR.MPQ", "locale-frFR.MPQ"]   # du + au - prioritaire
EN_MPQS = ["patch-enUS-3.MPQ", "patch-enUS-2.MPQ", "patch-enUS.MPQ", "locale-enUS.MPQ"]
NOM_TEXTES = "EbonholdFR_Glue.lua"
MARQUE = b"[EbonholdFR]"
CRLF = b"\r\n"


# ----------------------------------------------------------------------------- archives ---
def _patch_priority(name):
    """Rang d'un patch du dossier Data : patch, patch-2..9, patch-A..Z (le plus haut gagne)."""
    m = re.match(r"^patch(?:-([0-9A-Za-z]))?\.mpq$", name, re.I)
    if not m:
        return None
    c = m.group(1)
    if c is None:
        return 0
    return int(c) if c.isdigit() else 10 + ord(c.upper()) - ord("A")


class Sources:
    """Acces en lecture seule aux MPQ du joueur, dans l'ordre de priorite constate sur ce client :
    patchs du dossier Data (serveur) > patchs de langue frFR > ... (patch-Z exclu : c'est nous)."""

    def __init__(self, data_dir, ouvrir_mpq):
        self.data_dir = data_dir
        self.ouvrir = ouvrir_mpq
        self._cache = {}
        serveur = []
        for n in os.listdir(data_dir):
            p = _patch_priority(n)
            if p is not None and n.upper() != "PATCH-Z.MPQ":
                serveur.append((p, n))
        self.serveur_noms = [n for _, n in sorted(serveur, reverse=True)]
        self.fr_noms = [os.path.join("frFR", n) for n in FR_MPQS if os.path.isfile(os.path.join(data_dir, "frFR", n))]
        self.en_noms = [os.path.join("enUS", n) for n in EN_MPQS if os.path.isfile(os.path.join(data_dir, "enUS", n))]

    def _arc(self, nom):
        if nom not in self._cache:
            try:
                self._cache[nom] = self.ouvrir(os.path.join(self.data_dir, nom))
            except Exception:
                self._cache[nom] = None
        return self._cache[nom]

    def _lire(self, noms, interne):
        for nom in noms:
            a = self._arc(nom)
            if a is None:
                continue
            try:
                d = a.read(interne)
            except Exception:
                d = None
            if d:
                return d, nom
        return None, None

    def serveur(self, interne):
        return self._lire(self.serveur_noms, interne)

    def fr(self, interne):
        return self._lire(self.fr_noms, interne)

    def en(self, interne):
        return self._lire(self.en_noms, interne)

    def charge_par_le_jeu(self, interne):
        """Version que le client charge aujourd'hui (hors patch-Z) : serveur sinon pack FR."""
        d, n = self.serveur(interne)
        if d is None:
            d, n = self.fr(interne)
        return d, n

    def fermer(self):
        for a in self._cache.values():
            try:
                a.file.close()
            except Exception:
                pass


# ------------------------------------------------------------------ chaines Lua (Python) ---
_ESC = {ord("n"): 10, ord("t"): 9, ord("r"): 13, ord("a"): 7, ord("b"): 8, ord("f"): 12,
        ord("v"): 11, ord("\\"): 92, ord('"'): 34, ord("'"): 39}


class FormeInattendue(ValueError):
    pass


def lire_litteral(src, i):
    """Lit un litteral chaine Lua 5.1 a src[i] (bytes). Renvoie (valeur, fin, debut)."""
    debut = i
    q = src[i]
    if q in (34, 39):
        i += 1
        out = bytearray()
        while True:
            if i >= len(src):
                raise FormeInattendue("chaine non terminee")
            c = src[i]
            if c == q:
                return bytes(out), i + 1, debut
            if c in (10, 13):
                raise FormeInattendue("fin de ligne dans une chaine")
            if c == 92:
                i += 1
                c = src[i]
                if c in _ESC:
                    out.append(_ESC[c]); i += 1
                elif c in (10, 13):
                    out.append(10); i += 1
                    if i < len(src) and src[i] in (10, 13) and src[i] != c:
                        i += 1
                elif 48 <= c <= 57:
                    j = i
                    while j < len(src) and j - i < 3 and 48 <= src[j] <= 57:
                        j += 1
                    v = int(src[i:j])
                    if v > 255:
                        raise FormeInattendue("\\ddd > 255")
                    out.append(v); i = j
                else:
                    raise FormeInattendue("echappement inconnu \\%c" % c)
            else:
                out.append(c); i += 1
    if q == 91:  # [[ ... ]] ou [==[ ... ]==]
        m = re.compile(rb"\[(=*)\[").match(src, i)
        if not m:
            raise FormeInattendue("crochet inattendu")
        fin_motif = b"]" + m.group(1) + b"]"
        j = m.end()
        if src[j:j + 2] == b"\r\n":
            j += 2
        elif src[j:j + 1] in (b"\n", b"\r"):
            j += 1
        k = src.find(fin_motif, j)
        if k < 0:
            raise FormeInattendue("chaine longue non terminee")
        return src[j:k].replace(b"\r\n", b"\n"), k + len(fin_motif), debut
    raise FormeInattendue("pas une chaine")


def _sauter_blancs(src, i):
    while i < len(src):
        c = src[i:i + 1]
        if c in (b" ", b"\t", b"\r", b"\n"):
            i += 1
        elif src.startswith(b"--", i):
            m = re.compile(rb"--\[(=*)\[").match(src, i)
            if m:
                k = src.find(b"]" + m.group(1) + b"]", m.end())
                if k < 0:
                    raise FormeInattendue("commentaire long non termine")
                i = k + len(m.group(1)) + 2
            else:
                k = src.find(b"\n", i)
                i = len(src) if k < 0 else k + 1
        else:
            break
    return i


_IDENT = re.compile(rb"[A-Za-z_][A-Za-z0-9_]*")


def lire_glue_strings(src):
    """GlueStrings.lua -> liste ordonnee de (cle, valeur bytes, debut_litteral, fin_litteral).
    N'accepte QUE des affectations CLE = "chaine"; : toute autre forme leve FormeInattendue
    (on prefere alors ne rien traduire plutot que deviner)."""
    if src.startswith(b"\xef\xbb\xbf"):
        src = src[3:]
        decal = 3
    else:
        decal = 0
    i, out = 0, []
    while True:
        i = _sauter_blancs(src, i)
        if i >= len(src):
            break
        m = _IDENT.match(src, i)
        if not m or m.group() in (b"local", b"function", b"if", b"for", b"return", b"do", b"while"):
            raise FormeInattendue("instruction inattendue a l'octet %d" % i)
        cle = m.group().decode("ascii")
        i = _sauter_blancs(src, m.end())
        if src[i:i + 1] != b"=" or src[i:i + 2] == b"==":
            raise FormeInattendue("'=' attendu apres %s" % cle)
        i = _sauter_blancs(src, i + 1)
        val, fin, deb = lire_litteral(src, i)
        j = _sauter_blancs(src, fin)
        if src.startswith(b"..", j) or src[j:j + 1] in (b"(", b"[", b"."):
            raise FormeInattendue("expression (pas un simple litteral) pour %s" % cle)
        out.append((cle, val, deb + decal, fin + decal))
        i = fin
        k = _sauter_blancs(src, i)
        if src[k:k + 1] == b";":
            i = k + 1
    return out


def lua_chaine(b):
    """bytes -> litteral Lua 5.1 entre guillemets (UTF-8 conserve tel quel)."""
    out = bytearray(b'"')
    for c in b:
        if c == 92:
            out += b"\\\\"
        elif c == 34:
            out += b'\\"'
        elif c == 10:
            out += b"\\n"
        elif c == 13:
            out += b"\\r"
        elif c == 9:
            out += b"\\t"
        elif c < 32 or c == 127:
            out += b"\\%03d" % c
        else:
            out.append(c)
    out += b'"'
    return bytes(out)


def u8(s):
    return s.encode("utf-8") if isinstance(s, str) else s


def valeur_apres(src, motif, partiel=False):
    """Valeur d'un litteral (ou d'une concatenation de litteraux "a" .. "b") qui suit le motif regex.
    partiel=True : renvoie les litteraux lus avant le premier element non litteral."""
    m = re.search(motif, src)
    if not m:
        return None
    i = _sauter_blancs(src, m.end())
    morceaux = []
    while True:
        try:
            v, fin, _ = lire_litteral(src, i)
        except (FormeInattendue, IndexError):
            return b"".join(morceaux) if (partiel and morceaux) else None
        morceaux.append(v)
        j = _sauter_blancs(src, fin)
        if src.startswith(b"..", j):
            i = _sauter_blancs(src, j + 2)
            continue
        return b"".join(morceaux)


# --------------------------------------------------------------------------- controles ---
_SPEC = re.compile(rb"%(?:\d+\$)?[-+ #0]*\d*(?:\.\d+)?[sdifgxXcuoeE%]")
_ECH = re.compile(rb"\|(?:c[0-9A-Fa-f]{8}|r|T|t|n|H|h|1|2|3|4)")
_BALISE = re.compile(rb"</?[A-Za-z][^>]*>")


def compatibles(en, fr, strict):
    """Memes specificateurs de format (+ memes codes |c|r|T et balises HTML si strict)."""
    norm = lambda b: sorted(re.sub(rb"\d+\$", b"", s) for s in _SPEC.findall(b))
    if norm(en) != norm(fr):
        return False, "specificateurs de format differents"
    if strict:
        if sorted(_ECH.findall(en)) != sorted(_ECH.findall(fr)):
            return False, "codes |c/|r/|T differents"
        if _BALISE.findall(en) != _BALISE.findall(fr):
            return False, "balises HTML differentes"
    return True, ""


def est_url_pure(cle, val):
    return (cle.endswith("_URL") and b" " not in val.strip()) or re.fullmatch(rb"\s*https?://\S*\s*", val) is not None


def md5(b):
    return hashlib.md5(b).hexdigest()


# ----------------------------------------------------------------- Cfg_Categories.dbc ---
def lire_categories(b, col):
    """Cfg_Categories.dbc 3.3.5 : ID, LocaleMask, CharsetMask, Flags, Name_lang[16], flags -> {id: nom}."""
    mag, nrec, nfld, rsz, ssz = struct.unpack("<4s4I", b[:20])
    if mag != b"WDBC" or nfld != 21:
        raise ValueError("Cfg_Categories.dbc : format inattendu")
    chaines = b[20 + nrec * rsz:]
    out = {}
    for i in range(nrec):
        rec = struct.unpack("<%dI" % nfld, b[20 + i * rsz: 20 + (i + 1) * rsz])
        o = rec[4 + col]
        out[rec[0]] = chaines[o:chaines.find(b"\0", o)]
    return out


# ------------------------------------------------------------------------ generation ---
def generer_textes(poser, info):
    """EbonholdFR_Glue.lua : liste T(cle, anglais attendu, francais)."""
    L = [
        b"-- EbonholdFR : textes fran\xc3\xa7ais des \xc3\xa9crans de connexion, de choix du royaume et de personnage.",
        b"-- FICHIER G\xc3\x89N\xc3\x89R\xc3\x89 par le launcher EbonholdFR, ne pas modifier. " + u8(info),
        b"-- Un texte n'est remplac\xc3\xa9 que si le texte anglais actuel est EXACTEMENT celui attendu :",
        b"-- si le serveur change ou ajoute un texte, sa version anglaise reste affich\xc3\xa9e.",
        b"local G = _G or getfenv(0);",
        b"local vus, poses = 0, 0;",
        b"local function T(cle, en, fr)",
        b"\tvus = vus + 1;",
        b"\tif ( G[cle] == en ) then",
        b"\t\tG[cle] = fr;",
        b"\t\tposes = poses + 1;",
        b"\tend",
        b"end",
    ]
    for cle, en, fr in poser:
        L.append(b"T(" + lua_chaine(u8(cle)) + b", " + lua_chaine(en) + b", " + lua_chaine(fr) + b");")
    L.append(b"EBONHOLDFR_GLUE = { vus = vus, poses = poses };")
    L.append(b"")
    return CRLF.join(L)


def _lua_paires(d):
    """{cle: (en, fr)} -> { ["cle"] = { "en", "fr" }, ... }"""
    if not d:
        return b"{}"
    lignes = [b"\t[" + lua_chaine(u8(k)) + b"] = { " + lua_chaine(u8(en)) + b", " + lua_chaine(u8(fr)) + b" },"
              for k, (en, fr) in d.items()]
    return b"{" + CRLF + CRLF.join(lignes) + CRLF + b"}"


def _lua_motif(s):
    return re.sub(r"([\^\$\(\)%\.\[\]\*\+\-\?])", r"%\1", s)


POST_LUA = r'''
-- ===================== [EbonholdFR] debut du bloc genere (ne pas modifier) =====================
-- Traductions posees APRES le chargement de toute l'interface glue (RealmList.lua du serveur compris).
-- Un texte n'est remplace que s'il est identique a l'anglais attendu ; tout est protege par pcall.
local EbonholdFR_LocalizePost_avant = LocalizePost;
local EbonholdFR_GLOBALES = @GLOBALES@;
local EbonholdFR_DIALOGUES = @DIALOGUES@;
local EbonholdFR_CARTES = @CARTES@;
local EbonholdFR_ALIAS = @ALIAS@;
local EbonholdFR_DLL = @DLL@;

local function EbonholdFR_Post()
	local G = _G or getfenv(0);

	-- 1) globales texte definies par le serveur (cartes Live / PTR)
	for cle, t in pairs(EbonholdFR_GLOBALES) do
		if ( G[cle] == t[1] ) then
			G[cle] = t[2];
		end
	end

	-- 2) boites de dialogue deja declarees (ex. confirmation PTR)
	local types = G.GlueDialogTypes;
	if ( type(types) == "table" ) then
		for which, champs in pairs(EbonholdFR_DIALOGUES) do
			local d = types[which];
			if ( type(d) == "table" ) then
				for champ, t in pairs(champs) do
					if ( d[champ] == t[1] ) then
						d[champ] = t[2];
					end
				end
			end
		end
	end

	-- 3) textes ecrits en dur dans RealmList_SetupChoiceButton : corriges apres coup
	local C = EbonholdFR_CARTES;
	local setup = G.RealmList_SetupChoiceButton;
	if ( C and type(setup) == "function" ) then
		local function corriger(button)
			local nom = button and button.GetName and button:GetName();
			if ( type(nom) ~= "string" ) then
				return;
			end
			local royaume = G[nom.."Realm"];
			if ( royaume and royaume.GetText and royaume:GetText() == C.indispo_en ) then
				royaume:SetText(C.indispo_fr);
			end
			local statut = G[nom.."Status"];
			local texte = statut and statut.GetText and statut:GetText();
			if ( type(texte) == "string" ) then
				local nouveau = string.gsub(texte, C.motif_pluriel, C.remp_pluriel);
				nouveau = string.gsub(nouveau, C.motif_singulier, C.remp_singulier);
				if ( nouveau ~= texte ) then
					statut:SetText(nouveau);
				end
			end
		end
		G.RealmList_SetupChoiceButton = function(button, ...)
			local function apres(...)
				pcall(corriger, button);
				return ...;
			end
			return apres(setup(button, ...));
		end
	end

	-- 4) OPTION : categories de royaumes nommees dans la langue du client (Cfg_Categories.dbc)
	if ( EbonholdFR_ALIAS ) then
		local function pack(...)
			return { n = select("#", ...), ... };
		end
		local function alias(nomFonction)
			local f = G[nomFonction];
			if ( type(f) ~= "function" ) then
				return;
			end
			G[nomFonction] = function(nom, ...)
				local r = pack(f(nom, ...));
				local autres = EbonholdFR_ALIAS[nom];
				if ( r[1] == nil and autres ) then
					for i = 1, #autres do
						local r2 = pack(f(autres[i], ...));
						if ( r2[1] ~= nil ) then
							return unpack(r2, 1, r2.n);
						end
					end
				end
				return unpack(r, 1, r.n);
			end
		end
		alias("RealmList_FindRealmInCategory");
		alias("RealmWizard_FindCategory");
	end

	-- 5) OPTION : textes du controle de patchs (script glue de ebonhold.dll), traduits a l'affichage
	local D = EbonholdFR_DLL;
	local show = G.GlueDialog_Show;
	if ( D and type(show) == "function" ) then
		local function traduire(which, text)
			local types2 = G.GlueDialogTypes;
			local d = type(types2) == "table" and types2[which];
			local b = D.boutons[which];
			if ( type(d) == "table" and b ) then
				for champ, t in pairs(b) do
					if ( d[champ] == t[1] ) then
						d[champ] = t[2];
					end
				end
			end
			if ( type(text) ~= "string" ) then
				return text;
			end
			if ( D.textes[text] ) then
				return D.textes[text];
			end
			local debut, fin = string.find(text, D.suffixe_en, 1, true);
			if ( debut and D.textes[string.sub(text, 1, debut - 1)] ) then
				return D.textes[string.sub(text, 1, debut - 1)]..D.suffixe_fr..string.sub(text, fin + 1);
			end
			return text;
		end
		G.GlueDialog_Show = function(which, text, ...)
			local ok, nouveau = pcall(traduire, which, text);
			if ( ok ) then
				text = nouveau;
			end
			return show(which, text, ...);
		end
	end
end

function LocalizePost()
	if ( type(EbonholdFR_LocalizePost_avant) == "function" ) then
		EbonholdFR_LocalizePost_avant();
	end
	local ok, err = pcall(EbonholdFR_Post);
	EBONHOLDFR_POST = ok and "ok" or tostring(err);
end
-- ===================== [EbonholdFR] fin du bloc genere =====================
'''


def generer_post(base, tr, alias, avec_dll):
    glob = {k: (v["en"], v["fr"]) for k, v in tr["globales_post"].items()}
    dial = b"{" + CRLF
    for which, champs in tr["dialogues"].items():
        dial += b"\t[" + lua_chaine(u8(which)) + b"] = " + _lua_paires({c: (v["en"], v["fr"]) for c, v in champs.items()}).replace(CRLF, CRLF + b"\t") + b"," + CRLF
    dial += b"}"
    c = tr["cartes_royaume"]
    cartes = b"{ " + b", ".join([
        b"indispo_en = " + lua_chaine(b"Unavailable"),
        b"indispo_fr = " + lua_chaine(u8(c["Unavailable"])),
        b"motif_pluriel = " + lua_chaine(u8("(%d+) " + _lua_motif("characters") + "$")),
        b"remp_pluriel = " + lua_chaine(u8("%1 " + c["characters"].replace("%", "%%"))),
        b"motif_singulier = " + lua_chaine(u8("(%d+) " + _lua_motif("character") + "$")),
        b"remp_singulier = " + lua_chaine(u8("%1 " + c["character"].replace("%", "%%"))),
    ]) + b" }"
    if alias:
        a = b"{" + CRLF + CRLF.join(b"\t[" + lua_chaine(u8(en)) + b"] = { " + b", ".join(lua_chaine(u8(x)) for x in frs) + b" },"
                                     for en, frs in alias.items()) + CRLF + b"}"
    else:
        a = b"nil"
    if avec_dll:
        dd = tr["dialogues_dll"]
        bout = b"{" + CRLF + CRLF.join(
            b"\t\t[" + lua_chaine(u8(w)) + b"] = " + _lua_paires({ch: (v["en"], v["fr"]) for ch, v in champs.items()}).replace(CRLF, CRLF + b"\t\t") + b","
            for w, champs in dd["boutons"].items()) + CRLF + b"\t}"
        txt = b"{" + CRLF + CRLF.join(b"\t\t[" + lua_chaine(u8(t["en"])) + b"] = " + lua_chaine(u8(t["fr"])) + b"," for t in dd["textes"]) + CRLF + b"\t}"
        dll = (b"{" + CRLF + b"\tboutons = " + bout + b"," + CRLF + b"\ttextes = " + txt + b"," + CRLF +
               b"\tsuffixe_en = " + lua_chaine(u8(dd["suffixe_liste"]["en"])) + b"," + CRLF +
               b"\tsuffixe_fr = " + lua_chaine(u8(dd["suffixe_liste"]["fr"])) + b"," + CRLF + b"}")
    else:
        dll = b"nil"
    bloc = u8(POST_LUA).replace(b"\r\n", b"\n").replace(b"\n", CRLF)
    for k, v in ((b"@GLOBALES@", _lua_paires(glob)), (b"@DIALOGUES@", dial), (b"@CARTES@", cartes),
                 (b"@ALIAS@", a), (b"@DLL@", dll)):
        bloc = bloc.replace(k, v)
    base = base.rstrip(b"\r\n ") + CRLF
    return base + bloc


def generer_xml(base):
    """Ajoute <Script file="EbonholdFR_Glue.lua"/> avant le premier <Script> de GlueLocalization.xml."""
    if NOM_TEXTES.encode() in base:
        return base
    i = base.find(b"<Script")
    if i < 0:
        raise ValueError("GlueLocalization.xml : aucune balise <Script>")
    debut_ligne = base.rfind(b"\n", 0, i) + 1
    retrait = base[debut_ligne:i]
    if retrait.strip():
        retrait = b"\t"
    nl = CRLF if b"\r\n" in base else b"\n"
    ligne = b'<Script file="' + NOM_TEXTES.encode() + b'"/> <!-- ' + MARQUE + b" textes FR -->" + nl + retrait
    out = base[:i] + ligne + base[i:]
    racine = ET.fromstring(out)                       # doit rester du XML valide
    scripts = [e.get("file") for e in racine if e.tag.endswith("Script") and e.get("file")]
    if not scripts or scripts[0] != NOM_TEXTES:
        raise ValueError("GlueLocalization.xml : insertion incorrecte")
    return out


# --------------------------------------------------------------------------- coeur ---
def charger_traductions(chemin=None):
    with open(chemin or os.path.join(ICI, "traductions_glue.json"), encoding="utf-8") as f:
        return json.load(f)


def construire(data_dir, ouvrir_mpq, log=print, alias_categories=False, dialogues_dll=False,
               traductions=None, ref_en=None, variante_fusion=False):
    """Construit les fichiers glue FR a partir des fichiers ACTUELS du jeu. Ne modifie rien.
    En cas de doute sur un element, il est omis (anglais du serveur conserve) : jamais d'echec bloquant."""
    tr = traductions or charger_traductions()
    S = Sources(data_dir, ouvrir_mpq)
    R = {"date": datetime.datetime.now().isoformat(timespec="seconds"), "version_traductions": tr.get("version"),
         "fichiers": {}, "alertes": []}
    fichiers = {}
    try:
        # --- 1. textes : GlueStrings du serveur / Blizzard FR / Blizzard EN
        gs = GX + "GlueStrings.lua"
        srv, srv_arc = S.serveur(gs)
        fr, fr_arc = S.fr(gs)
        en, en_arc = S.en(gs)
        R["sources"] = {"serveur": srv_arc, "frFR": fr_arc, "enUS": en_arc or "empreintes ref_enUS_sha1.json"}
        if fr is None:
            log("Pack FR absent : ecrans glue laisses en anglais.")
            R["alertes"].append("pack frFR absent")
            return {}, R
        if srv is None:
            log("Le serveur ne remplace pas GlueStrings.lua : le pack FR s'applique deja tout seul.")
            R["alertes"].append("pas de GlueStrings serveur")
            return {}, R
        try:
            E = lire_glue_strings(srv)
            F = {k: v for k, v, _, _ in lire_glue_strings(fr)}
            U = {k: v for k, v, _, _ in lire_glue_strings(en)} if en else None
        except FormeInattendue as e:
            log("GlueStrings.lua : forme inattendue (%s) : ecrans laisses en anglais." % e)
            R["alertes"].append("GlueStrings forme inattendue : %s" % e)
            return {}, R
        if U is None:
            ref = ref_en
            if ref is None:
                p = os.path.join(ICI, "ref_enUS_sha1.json")
                ref = json.load(open(p, encoding="utf-8")) if os.path.isfile(p) else {}
            egal_blizzard = lambda k, v: ref.get(k) == hashlib.sha1(v).hexdigest()
        else:
            egal_blizzard = lambda k, v: k in U and U[k] == v
        trs = tr["GlueStrings"]
        poser, stats = [], {"blizzard_fr": 0, "ebonhold_fr": 0, "deja_identiques": 0, "url_exclues": 0,
                            "anglais_serveur_sans_trad": [], "trad_ebonhold_perimees": [], "incompatibles": []}
        vues = set()
        for k, v, _, _ in E:
            if k in vues:
                R["alertes"].append("cle en double dans GlueStrings serveur : %s (ignoree)" % k)
                poser = [p for p in poser if p[0] != k]
                continue
            vues.add(k)
            if k in trs:
                t_en, t_fr = u8(trs[k]["en"]), u8(trs[k]["fr"])
                if v == t_en:
                    ok, pourquoi = compatibles(v, t_fr, strict=True)
                    if ok:
                        poser.append((k, v, t_fr)); stats["ebonhold_fr"] += 1
                    else:
                        stats["incompatibles"].append("%s (%s)" % (k, pourquoi))
                    continue
                stats["trad_ebonhold_perimees"].append(k)
            if egal_blizzard(k, v) and k in F:
                if F[k] == v:
                    stats["deja_identiques"] += 1
                elif est_url_pure(k, v):
                    stats["url_exclues"] += 1
                else:
                    ok, pourquoi = compatibles(v, F[k], strict=False)
                    if ok:
                        poser.append((k, v, F[k])); stats["blizzard_fr"] += 1
                    else:
                        stats["incompatibles"].append("%s (%s)" % (k, pourquoi))
            elif k not in trs:
                stats["anglais_serveur_sans_trad"].append(k)
        stats["cles_serveur"] = len(vues)
        R["textes"] = stats
        info = "%s | serveur %s:GlueStrings.lua md5 %s | FR %s | traductions %s" % (
            R["date"], srv_arc, md5(srv), fr_arc, tr.get("version"))
        fichiers[GX + NOM_TEXTES] = generer_textes(poser, info)
        log("Ecrans glue : %d textes Blizzard FR + %d textes Ebonhold traduits, %d restent en anglais."
            % (stats["blizzard_fr"], stats["ebonhold_fr"], len(stats["anglais_serveur_sans_trad"]) + len(stats["trad_ebonhold_perimees"])))

        # --- 2. point d'entree precoce : GlueLocalization.xml (fichier Blizzard)
        xml, xml_arc = S.charge_par_le_jeu(GX + "GlueLocalization.xml")
        if xml is None:
            raise ValueError("GlueLocalization.xml introuvable")
        if xml_arc in S.serveur_noms:
            R["alertes"].append("GlueLocalization.xml vient du serveur (%s) : base serveur utilisee" % xml_arc)
        fichiers[GX + "GlueLocalization.xml"] = generer_xml(xml)
        R["fichiers"]["GlueLocalization.xml"] = {"base": xml_arc, "md5_base": md5(xml)}

        # --- 3. textes ecrits en dur par le serveur : GlueLocalizationPost.lua (fichier Blizzard)
        rl, rl_arc = S.serveur(GX + "RealmList.lua")
        verif = {}
        if rl:
            for k, v in tr["globales_post"].items():
                cur = valeur_apres(rl, rb"(?m)^\s*" + re.escape(k.encode()) + rb"\s*=")
                verif[k] = "ok" if cur == u8(v["en"]) else ("ABSENT" if cur is None else "TEXTE SERVEUR CHANGE")
            for which, champs in tr["dialogues"].items():
                bloc = re.search(rb'GlueDialogTypes\["' + re.escape(which.encode()) + rb'"\]\s*=\s*\{', rl)
                for champ, v in champs.items():
                    cur = valeur_apres(rl[bloc.end():], rb"\b" + re.escape(champ.encode()) + rb"\s*=") if bloc else None
                    verif[which + "." + champ] = "ok" if cur == u8(v["en"]) else ("ABSENT" if cur is None else "TEXTE SERVEUR CHANGE")
            for mot in ("Unavailable", "character", "characters"):
                verif["carte:" + mot] = "ok" if b'"' + mot.encode() + b'"' in rl else "ABSENT"
        R["textes_en_dur"] = verif
        alias = None
        if alias_categories:
            alias = {k: [v] for k, v in tr["alias_categories"].items()}
            try:
                dbc = "DBFilesClient\\Cfg_Categories.dbc"
                b_en, _ = S.en(dbc)
                b_fr, _ = S.charge_par_le_jeu(dbc)
                if b_en and b_fr:
                    ce, cf = lire_categories(b_en, 0), lire_categories(b_fr, 2)
                    calc = {}
                    for i, nom in ce.items():
                        if nom.decode("utf-8", "replace") in alias and cf.get(i) and cf[i] != nom:
                            calc.setdefault(nom.decode("utf-8"), [])
                            f2 = cf[i].decode("utf-8", "replace")
                            if f2 not in calc[nom.decode("utf-8")]:
                                calc[nom.decode("utf-8")].append(f2)
                    for k2, v2 in calc.items():
                        alias[k2] = v2
                    R["alias_categories"] = {"source": "Cfg_Categories.dbc enUS/frFR", "alias": alias}
            except Exception as e:
                R["alertes"].append("alias categories : %s (table de secours utilisee)" % e)
                R["alias_categories"] = {"source": "table de secours", "alias": alias}
        post, post_arc = S.charge_par_le_jeu(GX + "GlueLocalizationPost.lua")
        if post is None:
            post = b"function LocalizePost()\r\nend\r\n"
            post_arc = "(aucun : cree)"
        if MARQUE in post:
            raise ValueError("GlueLocalizationPost.lua contient deja un bloc EbonholdFR (base = patch-Z ?)")
        fichiers[GX + "GlueLocalizationPost.lua"] = generer_post(post, tr, alias, dialogues_dll)
        R["fichiers"]["GlueLocalizationPost.lua"] = {"base": post_arc, "md5_base": md5(post),
                                                      "alias_categories": bool(alias), "dialogues_dll": bool(dialogues_dll)}

        # --- 4. variante B (non recommandee) : GlueStrings.lua fusionne qui remplace celui du serveur
        if variante_fusion:
            out, pos = bytearray(), 0
            fr_de = {k: f for k, _, f in poser}
            for k, v, deb, fin in E:
                if k in fr_de:
                    out += srv[pos:deb] + lua_chaine(fr_de[k])
                    pos = fin
            out += srv[pos:]
            R["variante_fusion"] = {"cles_traduites": len(fr_de)}
            fichiers["variante_fusion\\" + GX + "GlueStrings.lua"] = bytes(out)
        R["fichiers"][NOM_TEXTES] = {"md5": md5(fichiers[GX + NOM_TEXTES])}
        R["source_serveur"] = {"GlueStrings.lua": {"archive": srv_arc, "md5": md5(srv)},
                               "RealmList.lua": {"archive": rl_arc, "md5": md5(rl) if rl else None}}
        return fichiers, R
    except Exception as e:  # jamais bloquant : on rend "rien" (anglais du serveur)
        log("Ecrans glue FR non construits (%s) : anglais conserve." % e)
        R["alertes"].append("ECHEC : %s" % e)
        return {}, R
    finally:
        S.fermer()


def verifier_lua(fichiers, log=print):
    """Syntaxe Lua 5.1 (lupa.lua51, comme WoW) + LuaJIT, si lupa est disponible."""
    try:
        import lupa
    except ImportError:
        log("lupa absent : verification syntaxique sautee (fichiers generes par construction).")
        return None
    res = {}
    for modname in ("lua51", "luajit21"):
        try:
            mod = __import__("lupa." + modname, fromlist=["LuaRuntime"])
        except ImportError:
            continue
        rt = mod.LuaRuntime(encoding=None)
        chk = rt.eval("function(s, n) local f, e = loadstring(s, n); return e end")
        for nom, data in fichiers.items():
            if nom.lower().endswith(".lua"):
                err = chk(data, ("=" + nom).encode())
                res["%s %s" % (modname, nom)] = "ok" if err is None else err.decode("utf-8", "replace")
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=r"C:\Users\Dylan\AppData\Local\ebonhold\Data")
    ap.add_argument("--out", default=os.path.join(ICI, "sortie"))
    ap.add_argument("--mpqread", default=os.path.join(os.path.dirname(ICI), "maj"))
    ap.add_argument("--alias-categories", action="store_true")
    ap.add_argument("--dialogues-dll", action="store_true")
    ap.add_argument("--variante-fusion", action="store_true")
    ap.add_argument("--generer-ref", action="store_true", help="ecrit ref_enUS_sha1.json depuis Data\\enUS")
    a = ap.parse_args()
    sys.path.insert(0, a.mpqread)
    import mpqread

    def ouvrir(p):
        return mpqread.Archive(p, listfile=False)

    if a.generer_ref:
        S = Sources(a.data, ouvrir)
        en, arc = S.en(GX + "GlueStrings.lua")
        S.fermer()
        ref = {k: hashlib.sha1(v).hexdigest() for k, v, _, _ in lire_glue_strings(en)}
        json.dump(ref, open(os.path.join(ICI, "ref_enUS_sha1.json"), "w", encoding="utf-8"), indent=0, sort_keys=True)
        print("ref_enUS_sha1.json : %d empreintes (%s)" % (len(ref), arc))
    fichiers, R = construire(a.data, ouvrir, alias_categories=a.alias_categories,
                             dialogues_dll=a.dialogues_dll, variante_fusion=a.variante_fusion)
    R["verification_lua"] = verifier_lua(fichiers)
    for nom, data in fichiers.items():
        p = os.path.join(a.out, *nom.split("\\"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(data)
        print("ecrit %-62s %7d o" % (nom, len(data)))
    with open(os.path.join(a.out, "rapport_glue.json"), "w", encoding="utf-8") as f:
        json.dump(R, f, ensure_ascii=False, indent=1)
    print(json.dumps({k: R[k] for k in R if k in ("alertes", "verification_lua", "textes_en_dur")}, ensure_ascii=False, indent=1))
    t = R.get("textes", {})
    print("textes : Blizzard FR %s, Ebonhold FR %s, deja identiques %s, URL exclues %s, anglais serveur sans trad %s, trad perimees %s, incompatibles %s"
          % (t.get("blizzard_fr"), t.get("ebonhold_fr"), t.get("deja_identiques"), t.get("url_exclues"),
             len(t.get("anglais_serveur_sans_trad", [])), t.get("trad_ebonhold_perimees"), t.get("incompatibles")))


if __name__ == "__main__":
    main()
