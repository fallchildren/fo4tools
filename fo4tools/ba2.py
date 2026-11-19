"""Bethesda BA2 (BTDX v1, GNRL) archives: read, list, extract, write.

Writer layout and hashes verified against the vanilla 'fallout4 - animations.ba2':
nameHash/dirHash = CRC32 variant (init 0, no final xor) over the lowercase base
name / lowercase backslash directory.
"""
import struct, os, re, zlib

REC = struct.Struct("<I4sIIQIII")  # hash, ext, dirHash, flags, offset, PAD, packed, unpacked

_TAB = []
for i in range(256):
    c = i
    for _ in range(8):
        c = (c >> 1) ^ 0xEDB88320 if c & 1 else c >> 1
    _TAB.append(c)

def bcrc(b):
    h = 0
    for x in b:
        h = (h >> 8) ^ _TAB[(h ^ x) & 0xFF]
    return h & 0xFFFFFFFF

# --- reading ----------------------------------------------------------------
def read(path):
    """-> list of dicts: name, ext, offset, packed, unpacked (raw entries)."""
    size = os.path.getsize(path)
    f = open(path, 'rb')
    hdr = f.read(24)
    magic, version, fmt = struct.unpack("<4sII", hdr[:12])
    if magic != b"BTDX":
        raise SystemExit("not a BA2: %r" % magic)
    if fmt != 0x4C524E47:  # 'GNRL'
        raise SystemExit("not a GNRL BA2 (DX10 textures? use dx10 module)")
    num, name_table_offset = struct.unpack("<IQ", hdr[12:24])
    table = f.read(24, REC.size * num)
    entries = []
    for i in range(num):
        h, ext, dh, flags, off, _pad, packed, unpacked = REC.unpack_from(table, i * REC.size)
        entries.append({"hash": h, "ext": ext.rstrip(b"\x00").decode("latin-1"),
                        "offset": off, "size": packed, "unpacked": unpacked, "name": None})
    start = 24 + name_table_offset
    names = f.read(start, size - start).split(b"\x00")
    names = [n for n in names if n]
    for e, n in zip(entries, names):
        txt = n.decode("latin-1").replace("\\", "/")
        m = re.search(r"\.(hkx|txt|nif|mat|xml|psc|swf|dds|wav|xwm|fuz)", txt, re.I)
        if m:
            txt = txt[:m.end()]
        e["name"] = txt
    entries[0]["_f"] = f  # keep the handle for extraction
    return entries, f

def list_names(path):
    entries, f = read(path)
    f.close()
    return [e["name"] for e in entries]

def extract_file(path, want, out_path):
    """Extract one file by (substring of) its archive name."""
    entries, f = read(path)
    for e in entries:
        if want.lower() in (e["name"] or "").lower():
            f.seek(e["offset"])
            data = f.read(e["size"])
            if e["size"] != e["unpacked"]:
                data = zlib.decompress(data)
            open(out_path, "wb").write(data)
            f.close()
            return e["name"]
    f.close()
    raise SystemExit("not found: %s" % want)

def extract_all(path, outdir, want=None):
    entries, f = read(path)
    n = 0
    for e in entries:
        if want and want.lower() not in (e["name"] or "").lower():
            continue
        f.seek(e["offset"])
        data = f.read(e["size"])
        if e["size"] != e["unpacked"]:
            data = zlib.decompress(data)
        dst = os.path.join(outdir, e["name"].replace("/", os.sep))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        open(dst, "wb").write(data)
        n += 1
    f.close()
    return n

# --- writing ----------------------------------------------------------------
def write_ba2(path, files):
    """files: list of (archive_name 'dir\\file.ext', bytes). Returns file count."""
    ents = []
    for name, data in files:
        n = name.replace('/', '\\')
        d, fn = n.lower().rsplit('\\', 1)
        base, ext = os.path.splitext(fn)
        ents.append((n, data, bcrc(base.encode()), ext[1:].encode()[:4].ljust(4, b'\0'), bcrc(d.encode())))
    n = len(ents)
    off = 24 + 36 * n
    recs = b''
    blob = b''
    for nm, data, nh, ext, dh in ents:
        recs += struct.pack('<I4sIIQIII', nh, ext, dh, 0x100100, off + len(blob), 0, len(data), 0xBAADF00D)
        blob += data
    nto = off + len(blob)
    names = b''.join(struct.pack('<H', len(nm.encode('latin1'))) + nm.encode('latin1') for nm, *_ in ents)
    open(path, 'wb').write(struct.pack('<4sI4sIQ', b'BTDX', 1, b'GNRL', n, nto) + recs + blob + names)
    return n
