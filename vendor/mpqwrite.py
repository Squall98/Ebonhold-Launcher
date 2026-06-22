"""Mini-createur d'archive MPQ v1 (format WoW 3.3.5a), fichiers compresses zlib en secteurs.
Suffisant pour empaqueter des .dbc lus par le client WoW. Auto-suffisant (aucune dependance externe)."""
import struct, zlib

def _prep_table():
    t = {}
    seed = 0x00100001
    for i in range(256):
        index = i
        for _ in range(5):
            seed = (seed * 125 + 3) % 0x2AAAAB
            t1 = (seed & 0xFFFF) << 0x10
            seed = (seed * 125 + 3) % 0x2AAAAB
            t2 = (seed & 0xFFFF)
            t[index] = (t1 | t2)
            index += 0x100
    return t

_TABLE = _prep_table()
_HT = {'TABLE_OFFSET': 0, 'HASH_A': 1, 'HASH_B': 2, 'TABLE': 3}

def _hash(s, htype):
    seed1 = 0x7FED7FED
    seed2 = 0xEEEEEEEE
    for ch in s.upper():
        c = ord(ch)
        value = _TABLE[(_HT[htype] << 8) + c]
        seed1 = (value ^ (seed1 + seed2)) & 0xFFFFFFFF
        seed2 = (c + seed1 + seed2 + (seed2 << 5) + 3) & 0xFFFFFFFF
    return seed1

def _encrypt(data, key):
    seed1 = key
    seed2 = 0xEEEEEEEE
    out = bytearray()
    for i in range(len(data) // 4):
        seed2 = (seed2 + _TABLE[0x400 + (seed1 & 0xFF)]) & 0xFFFFFFFF
        plain = struct.unpack_from("<I", data, i * 4)[0]
        enc = (plain ^ (seed1 + seed2)) & 0xFFFFFFFF
        seed1 = (((~seed1 << 0x15) & 0xFFFFFFFF) + 0x11111111) | (seed1 >> 0x0B)
        seed1 &= 0xFFFFFFFF
        seed2 = (plain + seed2 + (seed2 << 5) + 3) & 0xFFFFFFFF
        out += struct.pack("<I", enc)
    return bytes(out)

FILE_EXISTS   = 0x80000000
FILE_COMPRESS = 0x00000200

def _store_file(data, sector_size):
    """Decoupe en secteurs, compresse zlib (ou brut si pas mieux). Retourne (bytes_stockes, taille_decompressee)."""
    n = (len(data) + sector_size - 1) // sector_size
    sectors = []
    for i in range(n):
        raw = data[i * sector_size:(i + 1) * sector_size]
        comp = zlib.compress(raw, 9)
        cand = b"\x02" + comp  # 0x02 = zlib
        if len(cand) < len(raw):
            sectors.append(cand)
        else:
            sectors.append(raw)  # brut si pas plus petit
    # table des offsets de secteurs
    offt = (n + 1) * 4
    offsets = [offt]
    pos = offt
    for s in sectors:
        pos += len(s)
        offsets.append(pos)
    blob = bytearray()
    for o in offsets:
        blob += struct.pack("<I", o)
    for s in sectors:
        blob += s
    return bytes(blob), len(data)

def create_mpq(path, files, sector_shift=3):
    """files = dict {nom_interne(backslash): bytes}. Ecrit l'archive MPQ a `path`."""
    sector_size = 512 << sector_shift
    names = list(files.keys())
    # ajoute (listfile)
    listfile = ("\r\n".join(names) + "\r\n").encode("latin-1")
    entries = list(files.items()) + [("(listfile)", listfile)]

    HEADER = 32
    data_blob = bytearray()
    block_entries = []  # (offset_relatif_archive, csize, usize, flags)
    file_meta = []      # (nom, block_index)
    for idx, (name, content) in enumerate(entries):
        stored, usize = _store_file(content, sector_size)
        off = HEADER + len(data_blob)
        data_blob += stored
        block_entries.append((off, len(stored), usize, FILE_EXISTS | FILE_COMPRESS))
        file_meta.append((name, idx))

    # table de hash : taille = puissance de 2 >= 2*nb_fichiers
    hcount = 16
    while hcount < len(entries) * 2:
        hcount <<= 1
    hash_table = [[0xFFFFFFFF, 0xFFFFFFFF, 0xFFFF, 0xFFFF, 0xFFFFFFFF] for _ in range(hcount)]
    for name, bindex in file_meta:
        start = _hash(name, 'TABLE_OFFSET') % hcount
        a = _hash(name, 'HASH_A')
        b = _hash(name, 'HASH_B')
        i = start
        while hash_table[i][4] != 0xFFFFFFFF:
            i = (i + 1) % hcount
        hash_table[i] = [a, b, 0, 0, bindex]  # locale 0, platform 0

    # serialise tables
    ht = bytearray()
    for e in hash_table:
        ht += struct.pack("<IIHHI", e[0], e[1], e[2], e[3], e[4])
    bt = bytearray()
    for e in block_entries:
        bt += struct.pack("<IIII", e[0], e[1], e[2], e[3])

    ht_enc = _encrypt(bytes(ht), _hash("(hash table)", 'TABLE'))
    bt_enc = _encrypt(bytes(bt), _hash("(block table)", 'TABLE'))

    hash_pos = HEADER + len(data_blob)
    block_pos = hash_pos + len(ht_enc)
    archive_size = block_pos + len(bt_enc)

    header = struct.pack("<4sIIHHIIII",
        b"MPQ\x1a", HEADER, archive_size, 0, sector_shift,
        hash_pos, block_pos, hcount, len(block_entries))

    with open(path, "wb") as f:
        f.write(header)
        f.write(data_blob)
        f.write(ht_enc)
        f.write(bt_enc)
    return archive_size


if __name__ == "__main__":
    # Auto-test : cree un MPQ et le relit avec mpyq
    import mpyq, os
    test = {"DBFilesClient\\Test.dbc": b"WDBC" + b"HELLO_EBONHOLD_FR" * 1000}
    p = os.path.join(os.environ.get("TEMP", "."), "test_mpq.mpq")
    sz = create_mpq(p, test)
    print("MPQ cree:", sz, "octets")
    a = mpyq.MPQArchive(p)
    back = a.read_file("DBFilesClient\\Test.dbc")
    print("relecture OK:", back == test["DBFilesClient\\Test.dbc"], "| taille", len(back))
