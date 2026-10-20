"""Lecteur MPQ minimal, au-dessus de mpyq, qui gere aussi le chiffrement, LZMA et sparse.

mpyq (0.2.5) ne sait lire que zlib et bzip2 sans chiffrement ; les patchs Ebonhold
recents utilisent d'autres formats. Lecture seule.
"""
import bz2
import lzma
import struct
import zlib

import mpyq

F_IMPLODE = 0x00000100
F_COMPRESS = 0x00000200
F_ENCRYPTED = 0x00010000
F_FIX_KEY = 0x00020000
F_SINGLE = 0x01000000
F_CRC = 0x04000000
F_EXISTS = 0x80000000

def _decomp(data, expected):
    if len(data) >= expected:
        return data[:expected]
    t = data[0]
    body = data[1:]
    if t == 0x02:
        return zlib.decompress(body)
    if t == 0x10:
        return bz2.decompress(body)
    if t == 0x12:
        # StormLib : 1 octet de filtre (0) + 5 octets de proprietes + 8 octets de taille + flux
        if body[0] != 0:
            raise RuntimeError("LZMA avec filtre non gere")
        return lzma.decompress(body[1:], format=lzma.FORMAT_ALONE)[:expected]
    if t == 0x20:
        return _sparse(body, expected)
    if t == 0x22:   # sparse puis zlib
        return _sparse(zlib.decompress(body), expected)
    if t == 0x30:   # sparse puis bzip2
        return _sparse(bz2.decompress(body), expected)
    raise RuntimeError("compression 0x%02x non geree" % t)


def _sparse(data, expected):
    out = bytearray()
    i = 4  # taille sur 4 octets (big endian) en tete
    while i < len(data) and len(out) < expected:
        b = data[i]; i += 1
        if b & 0x80:
            n = (b & 0x7F) + 1
            out += data[i:i + n]; i += n
        else:
            n = (b & 0x7F) + 3
            out += b"\0" * n
    return bytes(out[:expected])


class Archive(mpyq.MPQArchive):
    def _key(self, filename, block):
        name = filename.replace("/", "\\").split("\\")[-1]
        key = self._hash(name, "TABLE")
        if block.flags & F_FIX_KEY:
            key = (key + block.offset) ^ block.size
        return key & 0xFFFFFFFF

    def read(self, filename):
        h = self.get_hash_table_entry(filename)
        if h is None:
            return None
        b = self.block_table[h.block_table_index]
        if not b.flags & F_EXISTS:
            return None
        if b.archived_size == 0:
            return b""
        if b.flags & F_IMPLODE:
            raise RuntimeError("PKWARE implode non gere")
        off = b.offset + self.header["offset"]
        self.file.seek(off)
        raw = self.file.read(b.archived_size)
        key = self._key(filename, b) if b.flags & F_ENCRYPTED else None
        if b.flags & F_SINGLE:
            if key is not None:
                raw = self._decrypt(raw, key)
            return _decomp(raw, b.size) if b.flags & F_COMPRESS else raw[:b.size]
        sector = 512 << self.header["sector_size_shift"]
        n = (b.size + sector - 1) // sector
        npos = n + 1 + (1 if b.flags & F_CRC else 0)
        posdata = raw[:4 * npos]
        if key is not None:
            posdata = self._decrypt(posdata, (key - 1) & 0xFFFFFFFF)
        pos = struct.unpack("<%dI" % npos, posdata)
        out = bytearray()
        for i in range(n):
            chunk = raw[pos[i]:pos[i + 1]]
            if key is not None:
                chunk = self._decrypt(chunk, (key + i) & 0xFFFFFFFF)
            want = min(sector, b.size - i * sector)
            out += _decomp(chunk, want) if b.flags & F_COMPRESS else chunk[:want]
        return bytes(out)


def names(arc):
    return [f.decode("latin1") for f in (arc.files or [])]
