#!/usr/bin/env python3
"""Tree-preserving plugin editor.

``espwrite.from_bytes`` flattens a plugin into a list of records, which loses the group
nesting (worldspace -> block -> sub-block -> cell -> children).  This module keeps the
tree, so a build step can load a finished plugin, change or add records, and write it back
without disturbing anything it did not touch.

    p = esptree.load(path)                  # Tree: header Record + top-level items
    note = p.find("NOTE", 0x02000940)       # a Record (anywhere in the tree)
    note.set("PTRN", struct.pack("<I", 0x000995A5))
    p.add_record(my_new_record)             # goes into the top-level group for its type
    p.write(path)                           # HEDR record count and next id are recomputed

Everything round-trips: ``serialize(load(x))`` re-renders every record from its parsed
subrecords with the stored header fields (flags, form version, version-control info), and
every group with its stored label, type, stamp and version.  Compressed records are
re-compressed (level 9), so a plugin written by this toolkit is byte-identical after a
load/serialize cycle; vanilla/Creation-Kit plugins are semantically identical (the zlib
stream bytes may differ).
"""
import struct
import zlib

from . import espwrite as W

# Order in which the top-level groups of a Fallout 4 plugin are emitted when a type is
# created from scratch (existing groups keep their position).
TOP_ORDER = ["GMST", "KYWD", "LCRT", "AACT", "TXST", "GLOB", "CLAS", "FACT", "HDPT", "EYES",
             "RACE", "SOUN", "ASPC", "MGEF", "ENCH", "SPEL", "ACTI", "TACT", "ARMO", "BOOK",
             "CONT", "DOOR", "INGR", "LIGH", "MISC", "STAT", "SCOL", "MSTT", "FLOR", "FURN",
             "WEAP", "AMMO", "NPC_", "LVLN", "KEYM", "ALCH", "IDLM", "NOTE", "COBJ", "PROJ",
             "HAZD", "LVLI", "WTHR", "CLMT", "REGN", "NAVI", "CELL", "WRLD", "QUST", "DIAL",
             "IDLE", "PACK", "TERM", "EFSH", "EXPL", "IMGS", "IMAD", "FLST", "PERK", "ADDN",
             "AVIF", "ARMA", "OMOD", "MSWP", "LENS", "LCTN", "MESG", "DOBJ", "LGTM", "MUSC",
             "SMBN", "SMQN", "SMEN"]


class Tree:
    """A whole plugin: the TES4 header record plus an ordered list of top-level Group/Record."""

    def __init__(self, header, items):
        self.header = header      # espwrite.Record (TES4)
        self.items = items        # espwrite.Group / espwrite.Record

    # ---------------------------------------------------------------- queries
    def walk(self):
        """Yield every Record (not groups) in file order."""
        def rec(items):
            for it in items:
                if isinstance(it, W.Group):
                    yield from rec(it.items)
                else:
                    yield it
        yield from rec(self.items)

    def find(self, sig, fid):
        for r in self.walk():
            if r.sig == sig and r.fid == fid:
                return r
        return None

    def masters(self):
        return [s.payload.split(b"\x00")[0].decode("latin1") for s in self.header.subs if s.sig == "MAST"]

    def top_group(self, sig):
        for it in self.items:
            if isinstance(it, W.Group) and it.group_type == 0 and _label_sig(it.label) == sig:
                return it
        return None

    def used_ids(self):
        return {r.fid for r in self.walk()}

    # ---------------------------------------------------------------- edits
    def add_record(self, rec):
        """Add a record to the top-level group for its type (created if missing)."""
        if rec.fid in self.used_ids():
            raise ValueError("FormID %08X is already in the plugin" % rec.fid)
        g = self.top_group(rec.sig)
        if g is None:
            g = W.Group(rec.sig, 0, 0, 0, [])
            self._insert_group(g)
        g.items.append(rec)
        return rec

    def remove(self, sig, fid):
        """Remove a record wherever it is. Returns True if something was removed."""
        def rm(items):
            for it in list(items):
                if isinstance(it, W.Group):
                    if rm(it.items):
                        return True
                elif it.sig == sig and it.fid == fid:
                    items.remove(it)
                    return True
            return False
        return rm(self.items)

    def _insert_group(self, g):
        sig = _label_sig(g.label)
        rank = TOP_ORDER.index(sig) if sig in TOP_ORDER else len(TOP_ORDER)
        at = len(self.items)
        for i, it in enumerate(self.items):
            if isinstance(it, W.Group) and it.group_type == 0:
                s = _label_sig(it.label)
                r = TOP_ORDER.index(s) if s in TOP_ORDER else len(TOP_ORDER)
                if r > rank:
                    at = i
                    break
        self.items.insert(at, g)

    # ---------------------------------------------------------------- output
    def counts(self):
        records = groups = 0

        def walk(items):
            nonlocal records, groups
            for it in items:
                if isinstance(it, W.Group):
                    groups += 1
                    walk(it.items)
                else:
                    records += 1
        walk(self.items)
        return records, groups

    def to_bytes(self, next_id=None):
        records, groups = self.counts()
        hedr = [s for s in self.header.subs if s.sig == "HEDR"]
        ver = struct.unpack("<f", hedr[0].payload[:4])[0] if hedr else 0.95
        old_next = struct.unpack("<I", hedr[0].payload[8:12])[0] if hedr else 0x800
        if next_id is None:
            highest = max([r.fid for r in self.walk() if (r.fid >> 24) == len(self.masters())] or [0])
            next_id = max(old_next, highest + 1)
        for s in self.header.subs:
            if s.sig == "HEDR":
                s.payload = struct.pack("<fII", ver, records + groups, next_id)
        out = bytearray(self.header.to_bytes())
        for it in self.items:
            out += it.to_bytes()
        return bytes(out)

    def write(self, path, next_id=None):
        data = self.to_bytes(next_id)
        with open(path, "wb") as f:
            f.write(data)
        return len(data)


def _label_sig(label):
    return (label.decode("latin1") if isinstance(label, (bytes, bytearray)) else label)[:4]


def parse(buf):
    """Parse plugin bytes into a :class:`Tree`."""
    def read(i, end):
        items = []
        while i + 24 <= end:
            sig = buf[i:i + 4]
            size = struct.unpack_from("<I", buf, i + 4)[0]
            if sig == b"GRUP":
                label = bytes(buf[i + 8:i + 12])
                gtype = struct.unpack_from("<i", buf, i + 12)[0]
                stamp, ver = struct.unpack_from("<HH", buf, i + 16)
                if i + size > end:
                    raise ValueError("group at %d overruns its parent" % i)
                items.append(W.Group(label, gtype, stamp, ver, read(i + 24, i + size)))
                i += size
            else:
                flags, fid = struct.unpack_from("<II", buf, i + 8)
                h = W.parse_record_header(buf, i)
                data = buf[i + 24:i + 24 + size]
                if flags & 0x00040000:
                    data = zlib.decompress(data[4:])
                items.append(W.Record(sig, fid, parse_subrecords(data), flags=flags,
                                      form_version=h["form_version"], vc=h["vc"],
                                      unknown=h["unknown"]))
                i += 24 + size
        return items

    top = read(0, len(buf))
    if not top or not isinstance(top[0], W.Record) or top[0].sig != "TES4":
        raise ValueError("not a plugin: no TES4 header")
    return Tree(top[0], top[1:])


def parse_subrecords(data):
    return [(s, p) for s, p in W.parse_subrecords(data)]


def load(path):
    with open(path, "rb") as f:
        return parse(f.read())
