"""Localisateur generique de DBC WotLK : detecte les blocs de chaines localisees
(16 locales + 1 flag) et remplit la colonne frFR (= enUS+2) depuis une version FR de base,
sinon recopie l'anglais (jamais vide)."""
import struct

def parse(buf):
    magic, rc, fc, rs, sbs = struct.unpack("<4sIIII", buf[:20])
    assert magic == b"WDBC", magic
    return rc, fc, rs, sbs, 20, buf[20 + rc*rs : 20 + rc*rs + sbs]

def getbytes(block, off):
    if off <= 0 or off >= len(block):
        return b""
    e = block.find(b"\x00", off)
    return block[off:e]

def _stats(buf):
    rc, fc, rs, sbs, rec_off, block = parse(buf)
    if rc == 0:
        return None
    step = max(1, rc // 3000)
    n = 0
    score = [0]*fc
    zero = [0]*fc
    for i in range(0, rc, step):
        o = rec_off + i*rs
        rec = struct.unpack_from("<%dI" % fc, buf, o)
        n += 1
        for fi in range(fc):
            v = rec[fi]
            if v == 0:
                zero[fi] += 1
            elif 0 < v < sbs:
                s = getbytes(block, v)
                if s and 32 <= s[0] < 127 and any(65 <= c <= 122 for c in s[:24]):
                    score[fi] += 1
    return n, score, zero, fc

def detect_blocks(buf, base_buf=None):
    """Candidats = champ a fort taux de texte suivi de 15 champs ~tous nuls (bloc locale enUS).
    Si base_buf fourni : ne garde que ceux dont la colonne +2 contient du texte FR dans la base."""
    st = _stats(buf)
    if st is None:
        return [], parse(buf)
    n, score, zero, fc = st
    cand = []
    for fi in range(fc - 16):
        if score[fi]/n > 0.03 and all(zero[fi+j]/n > 0.95 for j in range(1, 16)):
            cand.append(fi)
    if base_buf is not None:
        bst = _stats(base_buf)
        if bst is not None:
            bn, bscore, bzero, bfc = bst
            cand = [fi for fi in cand if fi+2 < bfc and bscore[fi+2]/bn > 0.03]
    # evite chevauchements : garde un bloc, saute 17
    blocks = []
    last = -17
    for fi in cand:
        if fi - last >= 17:
            blocks.append(fi); last = fi
    return blocks, parse(buf)

def merge(custom_buf, base_buf, tr=None, fr_col=2):
    """Retourne (new_dbc_bytes, stats). Priorite frFR : tr (trad manuelle, cle=texte EN)
    > texte FR de base (par id=champ0) > recopie de l'anglais. tr = dict {str_EN: str_FR}."""
    blocks, (rc, fc, rs, sbs, rec_off, cblock) = detect_blocks(custom_buf, base_buf)
    if not blocks:
        return None, {"blocks": 0}
    tr = tr or {}

    base_map = {}
    if base_buf is not None:
        brc, bfc, brs, bsbs, brec_off, bblock = parse(base_buf)
        for i in range(brc):
            o = brec_off + i*brs
            bid = struct.unpack_from("<I", base_buf, o)[0]
            vals = {}
            for b0 in blocks:
                if b0+2 < bfc:
                    off = struct.unpack_from("<I", base_buf, o + (b0+2)*4)[0]
                    vals[b0] = getbytes(bblock, off)  # texte FR de base = colonne +2
            base_map[bid] = vals

    pool = bytearray(b"\x00")
    offs = {b"": 0}
    def intern(s):
        if s in offs: return offs[s]
        o = len(pool); pool.extend(s); pool.append(0); offs[s] = o; return o

    def enc(s):
        return s.encode("utf-8")          # le client Ebonhold attend de l'UTF-8 (comme les chaînes de base)
    def dec(b):
        return b.decode("utf-8", "replace")

    new_records = bytearray()
    st_tr = st_base = st_copy = 0
    for i in range(rc):
        o = rec_off + i*rs
        rec = list(struct.unpack_from("<%dI" % fc, custom_buf, o))
        rid = rec[0]
        fr = base_map.get(rid)
        src = None
        for b0 in blocks:
            en = getbytes(cblock, rec[b0])
            frbytes = b""
            if en and dec(en) in tr:           # 1) trad manuelle (par texte EN)
                frbytes = enc(tr[dec(en)]); src = src or "tr"
            elif fr is not None and fr.get(b0): # 2) FR de base Blizzard
                frbytes = fr[b0]; src = src or "base"
            if not frbytes:                     # 3) recopie EN
                frbytes = en
            for k in range(16):
                rec[b0+k] = 0
            if fr_col == 0:
                rec[b0+0] = intern(frbytes)   # français dans la colonne enUS (client anglais, sans pack frFR)
            else:
                rec[b0+0] = intern(en)
                rec[b0+fr_col] = intern(frbytes)
        if src == "tr": st_tr += 1
        elif src == "base": st_base += 1
        else: st_copy += 1
        new_records.extend(struct.pack("<%dI" % fc, *rec))

    out = bytearray()
    out.extend(struct.pack("<4sIIII", b"WDBC", rc, fc, rs, len(pool)))
    out.extend(new_records)
    out.extend(pool)
    return bytes(out), {"blocks": blocks, "records": rc, "from_tr": st_tr, "from_base": st_base, "copied_en": st_copy, "strblock": len(pool)}


# Module utilitaire : importe-le depuis l'installeur / rebuild_all.py. Pas de point d'entree direct.
