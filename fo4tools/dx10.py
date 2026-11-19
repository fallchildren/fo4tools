#!/usr/bin/env python3
"""Minimal writer for Bethesda BA2 (BTDX v1, DX10) texture archives.

Layout verified against a working DX10 archive:
  header(24): 'BTDX' u32 1 'DX10' u32 numFiles u64 nameTableOffset(absolute)
  file records (24 each): u32 nameHash, u32 dirHash, 4s ext, u8 unk=0,
      u8 numChunks, u16 chunkHeaderSize=24, u16 height, u16 width,
      u8 numMips, u8 format(DXGI), u16 flags=0x0800
  chunk records (24 each, interleaved right after their file record):
      u64 dataOffset, u32 packedSize, u32 unpackedSize, u16 startMip,
      u16 endMip, u32 magic=0xBAADF00D
  data: zlib-compressed mip ranges (mips concatenated)
  name table: u16 len + name (backslashes)

nameHash/dirHash: the same CRC32 variant as the GNRL archives (init 0, no
final xor) over the lowercase base name / lowercase directory.
"""
import struct, zlib, os, sys

MAGIC = 0xBAADF00D

# DDS fourcc / DXGI format -> DX10 archive format code
DXGI = {28: ('R8G8B8A8', 4), 71: ('DXT1', 8), 72: ('DXT1', 8), 74: ('DXT3', 16),
        77: ('DXT5', 16), 80: ('ATI1', 8), 83: ('ATI2', 16), 87: ('B8G8R8A8', 4),
        95: ('BC6H', 16), 98: ('BC7', 16), 99: ('BC7', 16)}
FOURCC = {b'DXT1': 71, b'DXT3': 74, b'DXT5': 77, b'ATI1': 80, b'ATI2': 83,
          b'BC4U': 80, b'BC5U': 83, b'BC6H': 95, b'BC7 ': 98}

TAB = []
for i in range(256):
    c = i
    for _ in range(8):
        c = (c >> 1) ^ 0xEDB88320 if c & 1 else c >> 1
    TAB.append(c)

def bcrc(b):
    h = 0
    for x in b:
        h = (h >> 8) ^ TAB[(h ^ x) & 0xFF]
    return h & 0xFFFFFFFF

def parse_dds(data):
    """-> (w, h, mips, format_code, bytes_per_block, mip_sizes, pixel_offset)"""
    assert data[:4] == b'DDS '
    size, flags, h, w, pitch, depth, mips = struct.unpack_from('<7I', data, 4)
    mips = mips if mips else 1
    pf_flags, fourcc = struct.unpack_from('<II', data, 80)
    dxgi = 0
    if fourcc == 0x30315844:  # 'DX10'
        dxgi = struct.unpack_from('<I', data, 128)[0]
        fmt, bpb = DXGI[dxgi]
    else:
        fc = data[84:88]
        code = FOURCC.get(fc)
        if code is None:
            raise SystemExit("unsupported DDS fourcc %r" % fc)
        fmt, bpb = DXGI[code]
    sizes = []
    mw, mh = w, h
    for m in range(mips):
        if bpb:
            sizes.append(max(1, (mw + 3) // 4) * max(1, (mh + 3) // 4) * bpb)
        else:
            sizes.append(mw * mh * 4)
        mw, mh = max(1, mw >> 1), max(1, mh >> 1)
    return w, h, mips, dxgi if dxgi else FOURCC[fourcc.to_bytes(4, 'little')], bpb, sizes, 4 + size

def chunk_plan(nmips):
    """Bethesda-style chunking: mip 0 alone; mip 1 alone if >= 11 mips;
    mip 2 alone if >= 12 mips; the rest in one chunk."""
    if nmips >= 12:
        return [(0, 0), (1, 1), (2, 2), (3, nmips - 1)]
    if nmips >= 11:
        return [(0, 0), (1, 1), (2, nmips - 1)]
    if nmips > 1:
        return [(0, 0), (1, nmips - 1)]
    return [(0, 0)]

def write_ba2_dx10(path, files):
    """files: list of (archive_name 'dir\\file.dds', bytes)"""
    ents = []
    for name, data in files:
        n = name.replace('/', '\\')
        d, fn = n.lower().rsplit('\\', 1)
        base, ext = os.path.splitext(fn)
        w, h, mips, fmt, bpb, sizes, pixoff = parse_dds(data)
        raw = data[pixoff:]
        assert sum(sizes) <= len(raw), "DDS mip data short for %s" % n
        chunks = []
        for smip, emip in chunk_plan(mips):
            blob = b''.join(raw[sum(sizes[:m]):sum(sizes[:m + 1])] for m in range(smip, emip + 1))
            chunks.append((zlib.compress(blob), len(blob)))
        ents.append((n, d, base, ext, w, h, mips, fmt, chunks))

    n = len(ents)
    off = 24
    for e in ents:
        off += 24 + 24 * len(e[8])
    recs = b''
    blobs = b''
    for name, d, base, ext, w, h, mips, fmt, chunks in ents:
        nh = bcrc(base.encode())
        dh = bcrc(d.encode())
        recs += struct.pack('<II4sBBHHHBBH', nh, dh, ext.encode()[:4].ljust(4, b'\0'),
                            0, len(chunks), 24, h, w, mips, fmt, 0x0800)
        for (cdata, usize), (smip, emip) in zip(chunks, chunk_plan(mips)):
            recs += struct.pack('<QIIHHI', off + len(blobs), len(cdata), usize, smip, emip, MAGIC)
            blobs += cdata
    nto = off + len(blobs)
    names = b''.join(struct.pack('<H', len(nm.encode('latin1'))) + nm.encode('latin1')
                     for nm, *_ in ents)
    open(path, 'wb').write(struct.pack('<4sI4sIQ', b'BTDX', 1, b'DX10', n, nto) + recs + blobs + names)
    return n

if __name__ == '__main__':
    print("usage: import as module; write_ba2_dx10(path, files)")


# --- reading -----------------------------------------------------------------
def _read_index(path):
    """-> (file handle, names, records) with records = list of dicts."""
    f = open(path, 'rb')
    head = f.read(24)
    assert head[:4] == b'BTDX', "not a BA2"
    ver, btype, count = struct.unpack_from('<I4sI', head, 4)
    assert btype == b'DX10', "not a DX10 BA2"
    tpos = struct.unpack_from('<Q', head, 16)[0]
    f.seek(tpos)
    names = []
    for i in range(count):
        ln = struct.unpack('<H', f.read(2))[0]
        names.append(f.read(ln).decode('latin1').replace('\\', '/'))
    pos = 24
    records = []
    for i in range(count):
        f.seek(pos)
        nh, dh, ext, unk, nch, chhdr, h, w, mips, pfmt, flags = struct.unpack('<II4sBBHHHBBH', f.read(24))
        chunks = []
        for j in range(nch):
            off, psize, usize, smip, emip, magic = struct.unpack('<QIIHHI', f.read(24))
            chunks.append({'offset': off, 'packed': psize, 'unpacked': usize,
                           'start_mip': smip, 'end_mip': emip})
        pos += 24 + 24 * nch
        records.append({'name': names[i], 'w': w, 'h': h, 'mips': mips,
                        'format': pfmt, 'chunks': chunks})
    return f, records

def list_names(path):
    f, records = _read_index(path)
    f.close()
    return [r['name'] for r in records]

def mip_size(w, h, bpb):
    if bpb:
        return max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * bpb
    return w * h * 4

def dds_header(w, h, nmips, fourcc, bpb, is_dx10, pfmt):
    flags = 0x1 | 0x2 | 0x4 | 0x1000 | 0x80000 | (0x20000 if nmips > 1 else 0)
    hdr = b'DDS ' + struct.pack('<7I', 124, flags, h, w, mip_size(w, h, bpb), 0, nmips)
    hdr += b'\x00' * 44
    if is_dx10:
        hdr += struct.pack('<I', 32) + struct.pack('<I', 0x4) + b'DX10' + struct.pack('<5I', 0, 0, 0, 0, 0)
    else:
        hdr += struct.pack('<I', 32) + struct.pack('<I', 0x4) + fourcc.encode()
        hdr += struct.pack('<5I', 0, 0, 0, 0, 0)
    hdr += struct.pack('<5I', 0x1000, 0, 0, 0, 0)
    if is_dx10:
        hdr += struct.pack('<5I', pfmt, 3, 0, 1, 0)
    return hdr

def extract_all(path, outdir, want=None):
    """Extract every texture as a full-mip .dds. Returns count."""
    f, records = _read_index(path)
    n = 0
    for r in records:
        if want and want.lower() not in r['name'].lower():
            continue
        fmt, bpb = DXGI[r['format']]
        is_dx10 = r['format'] in (95, 98, 99)
        fourcc = fmt if not is_dx10 else 'DX10'
        mips = []
        for c in sorted(r['chunks'], key=lambda c: c['start_mip']):
            f.seek(c['offset'])
            raw = f.read(c['packed'])
            try:
                data = zlib.decompress(raw) if raw[:2] in (b'\x78\x9c', b'\x78\x01', b'\x78\xda') else zlib.decompress(raw, -15)
            except Exception:
                continue
            mw, mh = r['w'] >> c['start_mip'], r['h'] >> c['start_mip']
            p = 0
            for m in range(c['start_mip'], c['end_mip'] + 1):
                sz = mip_size(mw, mh, bpb)
                mips.append(data[p:p + sz]); p += sz
                mw, mh = max(1, mw >> 1), max(1, mh >> 1)
        dst = os.path.join(outdir, r['name'].replace('/', os.sep))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        open(dst, 'wb').write(dds_header(r['w'], r['h'], len(mips), fourcc, bpb, is_dx10, r['format']) + b''.join(mips))
        n += 1
    f.close()
    return n
