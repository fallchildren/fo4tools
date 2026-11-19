#!/usr/bin/env python3
# Minimal FO4 NiStream parser for the weapon nifs (44.nif family):
# reads BSTriShape geometry (positions, UVs, normals, triangles), the NiNode hierarchy transforms,
# and the BSLightingShaderProperty -> BSShaderTextureSet texture paths.
import struct, math

def _half(h):
    s = (h >> 15) & 1; e = (h >> 10) & 0x1F; m = h & 0x3FF
    if e == 0: v = m * 2**-24
    elif e == 31: v = float('inf') if m == 0 else float('nan')
    else: v = (1 + m / 1024.0) * 2 ** (e - 15)
    return -v if s else v

class Nif:
    def __init__(self, path):
        self.f = open(path, 'rb')
        self.strs = []
        self.blocks = []          # (type_name, data_offset, data_size)
        self._parse_header()

    def _parse_header(self):
        f = self.f
        f.readline()                                    # "Gamebryo File Format, Version 20.2.0.7"
        ver, = struct.unpack('<I', f.read(4))
        endian, = struct.unpack('<B', f.read(1))
        user_ver, = struct.unpack('<I', f.read(4))
        num_blocks, = struct.unpack('<I', f.read(4))
        bs_ver, = struct.unpack('<I', f.read(4))
        # BSStreamHeader ExportStrings: u8 length + chars (4 of them, BSVersion < 131)
        for _ in range(4):
            (ln,) = struct.unpack('<B', f.read(1))
            f.read(ln)
        num_types, = struct.unpack('<H', f.read(2))
        types = []
        for _ in range(num_types):
            (ln,) = struct.unpack('<I', f.read(4))
            types.append(f.read(ln).decode('latin1', 'replace').rstrip('\x00'))
        type_idx = struct.unpack('<%dH' % num_blocks, f.read(2 * num_blocks))
        sizes = struct.unpack('<%dI' % num_blocks, f.read(4 * num_blocks))
        num_strs, max_len = struct.unpack('<II', f.read(8))
        for _ in range(num_strs):
            (ln,) = struct.unpack('<I', f.read(4))
            self.strs.append(f.read(ln).decode('latin1', 'replace').rstrip('\x00'))
        num_groups, = struct.unpack('<I', f.read(4))
        for _ in range(num_groups):
            (gn,) = struct.unpack('<I', f.read(4))
            f.read(4 * gn)
            (gb,) = struct.unpack('<I', f.read(4))
            f.read(2 * gb)
        self.user_ver = user_ver
        off = f.tell()
        for i in range(num_blocks):
            self.blocks.append((types[type_idx[i]], off, sizes[i]))
            off += sizes[i]

    def read_at(self, off, fmt):
        self.f.seek(off)
        return struct.unpack(fmt, self.f.read(struct.calcsize(fmt)))

    def block_data(self, i):
        _, off, size = self.blocks[i]
        self.f.seek(off)
        return self.f.read(size)

    def str_of(self, idx):
        return self.strs[idx] if 0 <= idx < len(self.strs) else ''

    # NiAVObject header (FO4): name, extra data, controller, flags(u32), translation, rotation(3x3), scale,
    # then velocity? no - FO4: translation, rotation, scale, collision object (no velocity/properties here)
    def parse_av(self, i, pos=0):
        name_idx, = self.read_at(self.blocks[i][1] + pos, '<i')
        pos += 4
        (ne,) = self.read_at(self.blocks[i][1] + pos, '<I'); pos += 4 + 4 * ne
        ctrl, = self.read_at(self.blocks[i][1] + pos, '<i'); pos += 4
        flags, = self.read_at(self.blocks[i][1] + pos, '<I'); pos += 4
        trans = self.read_at(self.blocks[i][1] + pos, '<3f'); pos += 12
        rot = self.read_at(self.blocks[i][1] + pos, '<9f'); pos += 36
        scale, = self.read_at(self.blocks[i][1] + pos, '<f'); pos += 4
        coll, = self.read_at(self.blocks[i][1] + pos, '<i'); pos += 4
        return pos, trans, rot, scale

    def parse(self):
        out = {'meshes': [], 'nodes': {}}
        for i, (t, off, size) in enumerate(self.blocks):
            if t == 'BSTriShape':
                pos, trans, rot, scale = self.parse_av(i)
                m = self.parse_trishape(i, pos, trans, rot, scale)
                if m is not None:
                    out['meshes'].append(m)
            elif t == 'NiNode':
                pos, trans, rot, scale = self.parse_av(i)
                (nc,) = self.read_at(off + pos, '<I'); pos += 4
                children = self.read_at(off + pos, '<%di' % nc) if nc else ()
                out['nodes'][i] = {'trans': trans, 'children': children}
        return out

    def parse_trishape(self, i, pos, trans, rot, scale):
        off = self.blocks[i][1]
        # bounding sphere
        center = self.read_at(off + pos, '<3f'); radius, = self.read_at(off + pos + 12, '<f'); pos += 16
        skin, shader, alpha = self.read_at(off + pos, '<3i'); pos += 12
        desc, = self.read_at(off + pos, '<Q'); pos += 8
        ntris, = self.read_at(off + pos, '<I'); pos += 4
        nverts, = self.read_at(off + pos, '<H'); pos += 2
        dsize, = self.read_at(off + pos, '<I'); pos += 4
        # Data Size covers BOTH the vertex block and the index block (nif.xml): tris are the tail
        self.f.seek(off + pos)
        block = self.f.read(dsize)
        pos += dsize
        tri_bytes = ntris * 6
        vdata = block[:dsize - tri_bytes]
        tris = struct.unpack('<%dH' % (ntris * 3), block[dsize - tri_bytes:dsize])
        # The vertex layout flags live in the HIGH bits of the descriptor (nif.xml: "Vertex Desc RSH 44")
        arg = desc >> 44
        verts = []
        p = 0
        for v in range(nverts):
            if (arg & 0x401) == 0x401:                 # full float3
                px, py, pz = struct.unpack_from('<3f', vdata, p); p += 12
            else:                                      # half3
                hx, hy, hz = struct.unpack_from('<3H', vdata, p); p += 6
                px, py, pz = _half(hx), _half(hy), _half(hz)
            if (arg & 0x411) == 0x411: p += 4          # bitangent X float + unused
            elif (arg & 0x411) == 0x11: p += 2         # bitangent X half
            elif (arg & 0x411) == 0x1: p += 2          # unused W
            u = vv = 0.0
            if arg & 0x2:
                hu, hv = struct.unpack_from('<2H', vdata, p); p += 4
                u, vv = _half(hu), 1.0 - _half(hv)
            nx = ny = nz = 0.0
            if arg & 0x8:
                bx, by, bz, _bw = struct.unpack_from('<4b', vdata, p); p += 4
                nx, ny, nz = bx / 127.0, by / 127.0, bz / 127.0
            if (arg & 0x18) == 0x18:
                p += 4
            if arg & 0x20:
                p += 4
            if arg & 0x40:
                p += 12
            if arg & 0x100:
                p += 4
            verts.append(((px, py, pz), (u, vv), (nx, ny, nz)))
        # properties
        (np_,) = self.read_at(off + pos, '<I'); pos += 4
        props = self.read_at(off + pos, '<%di' % np_)
        tex = None
        for pr in props:
            if 0 <= pr < len(self.blocks) and self.blocks[pr][0] == 'BSLightingShaderProperty':
                tex = self.texture_set_of(pr)
        return {'verts': verts, 'tris': list(tris), 'trans': trans, 'rot': rot, 'scale': scale, 'textures': tex}

    def texture_set_of(self, i):
        off = self.blocks[i][1]
        name_idx, = self.read_at(off, '<i')
        flags, = self.read_at(off + 4, '<H')
        # FO4 BSLightingShaderProperty (userVersion < 132): shader flags 1+2, UV off/scale, texture set ref
        sf1, sf2 = self.read_at(off + 6, '<II')
        uvoff = self.read_at(off + 14, '<2f')
        uvscale = self.read_at(off + 22, '<2f')
        tref, = self.read_at(off + 30, '<i')
        if 0 <= tref < len(self.blocks) and self.blocks[tref][0] == 'BSShaderTextureSet':
            toff = self.blocks[tref][1]
            (nt,) = self.read_at(toff, '<I')
            idxs = self.read_at(toff + 4, '<%di' % nt)
            return [self.str_of(x) for x in idxs]
        return None


if __name__ == '__main__':
    import sys, json
    n = Nif(sys.argv[1])
    out = n.parse()
    print(json.dumps(out, indent=1, default=str)[:3000])
