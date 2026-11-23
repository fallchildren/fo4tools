#!/usr/bin/env python3
"""Fallout 4 plugin writer: subrecords, records, groups, TES4 header.

The write-side counterpart to :mod:`fo4tools.espread`.  Pure stdlib, no zlib
dependencies beyond what the format needs.  Everything here round-trips:
``serialize_subrecords(parse_subrecords(x)) == x`` for every subrecord stream
in Fallout4.esm (see ``test_espwrite``).

Layout reminders (TES4/FO4):

    Record header (24 bytes, uncompressed):
        sig[4]  u32 dataSize  u32 flags  u32 formID  u16 vc  u16 version  u16 pad?
        For FO4 the 24-byte header is: sig, size, flags, formID,
                                       vc(2), formVersion(2), pad(4)   -> 24 bytes
        Compressed records (flags & 0x00040000) put u32 compressedSize at
        offset 20 and the zlib stream at 24; the 4 ``pad`` bytes are replaced by
        the size, so compressed header is still 24 bytes.

    Subrecord: sig[4] u16 size payload
    Extended:  sig "XXXX" u32 realSize  -> the *next* subrecord uses realSize

    Group: "GRUP" u32 size label[4] i32 groupType u16 stamp u16 version
           u32? -> the FO4 group header is 24 bytes total (see make_group).

Use :func:`to_bytes` / :func:`from_bytes` for whole plugins, or the individual
``render_*`` helpers when assembling by hand.
"""
import struct
import zlib

__all__ = [
    "parse_subrecords", "serialize_subrecords",
    "Subrecord", "Record", "Group", "Plugin",
    "render_record", "render_group", "render_tes4",
    "to_bytes", "from_bytes", "SIG_TES4",
]


# --------------------------------------------------------------------------
# Subrecords
# --------------------------------------------------------------------------
def parse_subrecords(data):
    """Parse a record's payload into ``[(sig_str, payload_bytes), ...]``.

    Handles the ``XXXX`` extended-size escape (a subrecord longer than 0xFFFF
    bytes).  The ``XXXX`` marker is *not* returned; the following subrecord's
    size comes from it.  This is the inverse of :func:`serialize_subrecords`.
    """
    out = []
    i = 0
    n = len(data)
    xxxx = None
    while i + 6 <= n:
        sig = data[i:i + 4].decode("latin1")
        size = struct.unpack_from("<H", data, i + 4)[0]
        i += 6
        if sig == "XXXX":
            if i + 4 > n:
                raise ValueError("truncated XXXX at %d" % i)
            xxxx = struct.unpack_from("<I", data, i)[0]
            i += 4
            continue
        if xxxx is not None:
            size = xxxx
            xxxx = None
        if i + size > n:
            raise ValueError("subrecord %r at %d overruns payload (need %d, have %d)"
                             % (sig, i, size, n - i))
        out.append((sig, data[i:i + size]))
        i += size
    return out


def _subrecord_bytes(sig, payload):
    if len(payload) > 0xFFFF:
        # XXXX escape: a normal subrecord ``XXXX`` + u16 size(4) + u32 realSize,
        # placed BEFORE the target subrecord.  The target keeps its own u16 size
        # field, written as 0 (readers take the real size from XXXX).
        return (b"XXXX" + struct.pack("<HI", 4, len(payload))
                + sig.encode("latin1") + b"\x00\x00" + payload)
    return sig.encode("latin1") + struct.pack("<H", len(payload)) + payload


def serialize_subrecords(subs):
    """Serialise ``[(sig, payload), ...]`` back to a record payload.

    Values longer than 0xFFFF bytes are emitted with the ``XXXX`` escape so the
    stream stays valid.  Exact inverse of :func:`parse_subrecords`.
    """
    out = bytearray()
    for sig, payload in subs:
        if isinstance(sig, bytes):
            sig = sig.decode("latin1")
        out += _subrecord_bytes(sig, payload)
    return bytes(out)


class Subrecord:
    """A sig/payload pair with ``as_int`` / ``as_str`` conveniences."""
    __slots__ = ("sig", "payload")

    def __init__(self, sig, payload=b""):
        self.sig = sig.decode("latin1") if isinstance(sig, bytes) else sig
        self.payload = bytes(payload)

    # -- typed accessors ---------------------------------------------------
    def as_u32(self, off=0):
        return struct.unpack_from("<I", self.payload, off)[0]

    def as_u16(self, off=0):
        return struct.unpack_from("<H", self.payload, off)[0]

    def as_str(self):
        return self.payload.split(b"\x00")[0].decode("latin1")

    def as_u32_tuple(self):
        return [struct.unpack_from("<I", self.payload, i)[0]
                for i in range(0, len(self.payload) - 3, 4)]

    def __repr__(self):
        return "Subrecord(%r, %d bytes)" % (self.sig, len(self.payload))


# --------------------------------------------------------------------------
# Records
# --------------------------------------------------------------------------
def render_record(sig, fid, subrecords, flags=0, form_version=131, vc=0,
                  unknown=0, compress=False, compress_level=9):
    """Build one record.

    ``sig``          4 chars, ``fid`` int, ``subrecords`` list of (sig, payload).
    ``flags``        32-bit record flags (bit 0x00040000 = compressed).
    ``form_version`` FO4 internal form version (131 for CK-written records; the
                     reader exposes 131 for most vanilla records).
    ``vc``           version control info (u32 @16).
    ``unknown``      u16 @22 (CK writes 0 for new records; copy-preserved).
    ``compress``     zlib-compress the payload.

    Header layout (24 bytes, FO4):
        sig[4] size(u32) flags(u32) formID(u32) vc(u32) formVersion(u16) unknown(u16)
    When compressed, ``vc`` is replaced by the u32 compressed size and the
    unknown u16 pair stays at 20.. no: compression puts compressedSize @20 and
    leaves formVersion/unknown where they are -- see below.
    """
    if isinstance(sig, str):
        sig = sig.encode("latin1")
    payload = serialize_subrecords(subrecords)

    if compress:
        flags |= 0x00040000
        body = zlib.compress(payload, compress_level)
        # Real layout (checked against Fallout4.esm): the data is
        #   u32 DECOMPRESSED length, then the zlib stream,
        # and the header's dataSize is 4 + len(stream).  (Earlier versions wrote the
        # compressed length into the u32 and decompressed+4 into dataSize, which
        # corrupts every group that follows the record.)
        return (sig + struct.pack("<III", len(body) + 4, flags, fid)
                + struct.pack("<IHH", vc, form_version, unknown)
                + struct.pack("<I", len(payload)) + body)

    flags &= ~0x00040000
    return (sig + struct.pack("<III", len(payload), flags, fid)
            + struct.pack("<IHH", vc, form_version, unknown)
            + payload)


def parse_record_header(buf, off=0):
    """Return dict describing the record header at ``off`` (does not decompress)."""
    sig = buf[off:off + 4]
    size, flags, fid = struct.unpack_from("<III", buf, off + 4)
    vc = struct.unpack_from("<I", buf, off + 16)[0]
    form_version, unknown = struct.unpack_from("<HH", buf, off + 20)
    compressed = bool(flags & 0x00040000)
    payload_off = off + 24
    total = 24 + size
    if compressed:
        # dataSize = 4 (decompressed-length prefix) + zlib stream; ``size`` is the stream
        # length, ``total`` is the whole record on disk.
        total = 24 + size
        size = size - 4
        payload_off = off + 24
    return {
        "sig": sig, "size": size, "flags": flags, "fid": fid,
        "vc": vc, "form_version": form_version, "unknown": unknown,
        "compressed": compressed, "payload_off": payload_off,
        "total": total,
    }


class Record:
    """A mutable record: sig, fid, flags, form_version, and ordered subrecords."""
    __slots__ = ("sig", "fid", "flags", "form_version", "vc", "unknown", "subs")

    def __init__(self, sig, fid, subs=None, flags=0, form_version=131, vc=0,
                 unknown=0):
        self.sig = sig.decode("latin1") if isinstance(sig, bytes) else sig
        self.fid = fid
        self.flags = flags
        self.form_version = form_version
        self.vc = vc
        self.unknown = unknown
        self.subs = [Subrecord(s, p) for s, p in (subs or [])]

    # -- subrecord access --------------------------------------------------
    def get(self, sig, default=None):
        for s in self.subs:
            if s.sig == sig:
                return s
        return default

    def get_payload(self, sig, default=None):
        s = self.get(sig)
        return s.payload if s is not None else default

    def set(self, sig, payload):
        """Set (replace first, else append) a subrecord."""
        if isinstance(sig, bytes):
            sig = sig.decode("latin1")
        for s in self.subs:
            if s.sig == sig:
                s.payload = bytes(payload)
                return self
        self.subs.append(Subrecord(sig, payload))
        return self

    def remove(self, sig):
        self.subs = [s for s in self.subs if s.sig != sig]
        return self

    def has(self, sig):
        return self.get(sig) is not None

    @property
    def edid(self):
        p = self.get_payload("EDID")
        return p.split(b"\x00")[0].decode("latin1") if p else None

    def to_bytes(self, compress=None):
        if compress is None:
            compress = bool(self.flags & 0x00040000)
        return render_record(self.sig, self.fid, [(s.sig, s.payload) for s in self.subs],
                             flags=self.flags, form_version=self.form_version,
                             vc=self.vc, unknown=self.unknown, compress=compress)

    def __repr__(self):
        return "Record(%s %08X edid=%r, %d subs)" % (self.sig, self.fid, self.edid, len(self.subs))


# --------------------------------------------------------------------------
# Groups
# --------------------------------------------------------------------------
def render_group(label, children, group_type=0, stamp=0, version=0):
    """Build a GRUP.  ``children`` is a concatenation of already-rendered bytes.

    ``label`` for a top-level record group is the 4-char sig (e.g. ``ARMO``).
    Group header is 24 bytes: GRUP, size, label[4], type(i32), stamp(u16),
    version(u16), pad(u32).
    """
    if isinstance(label, str):
        label = label.encode("latin1")
    label = label[:4].ljust(4, b"\x00")
    body = b"".join(children) if not isinstance(children, (bytes, bytearray)) else bytes(children)
    size = 24 + len(body)
    return (b"GRUP" + struct.pack("<I", size) + label
            + struct.pack("<i", group_type)
            + struct.pack("<HH", stamp, version)
            + struct.pack("<I", 0)
            + body)


class Group:
    """A GRUP holding records and/or nested groups."""
    __slots__ = ("label", "group_type", "stamp", "version", "items")

    def __init__(self, label, group_type=0, stamp=0, version=0, items=None):
        self.label = label
        self.group_type = group_type
        self.stamp = stamp
        self.version = version
        self.items = list(items or [])

    def add(self, item):
        self.items.append(item)
        return self

    def to_bytes(self):
        return render_group(self.label, [i.to_bytes() if hasattr(i, "to_bytes")
                                          else i for i in self.items],
                            self.group_type, self.stamp, self.version)

    def __repr__(self):
        return "Group(%r type=%d, %d items)" % (self.label, self.group_type, len(self.items))


# --------------------------------------------------------------------------
# Plugin / TES4 header
# --------------------------------------------------------------------------
SIG_TES4 = b"TES4"
FLAG_ESM = 0x00000001
FLAG_LOCALIZED = 0x00000080
FLAG_ESL = 0x00000200


def render_tes4(masters, flags=0, version=0.95, num_records=0, next_id=0x800,
                author=None, description=None, compress=False):
    """Build the TES4 header record.

    ``masters`` list of plugin filenames, in load order (Fallout4.esm first).
    For ESL-flagged plugins ``next_id`` should live in the object range.
    """
    subs = []
    hedr = struct.pack("<fII", version, num_records, next_id)
    subs.append(("HEDR", hedr))
    if author is not None:
        subs.append(("CNAM", author.encode("latin1") + b"\x00"))
    if description is not None:
        subs.append(("SNAM", description.encode("latin1") + b"\x00"))
    for m in masters:
        if isinstance(m, str):
            m = m.encode("latin1")
        subs.append(("MAST", m if m.endswith(b"\x00") else m + b"\x00"))
        # DATA: u64 (unused by the engine; CK writes 0)
        subs.append(("DATA", struct.pack("<Q", 0)))
    return render_record("TES4", 0, subs, flags=flags, form_version=0, vc=0,
                         compress=compress)


class Plugin:
    """In-memory plugin: header fields plus an ordered list of groups/records."""

    def __init__(self, masters=None, flags=FLAG_ESL, version=0.95,
                 next_id=0x800, author=None, description=None):
        self.masters = list(masters or ["Fallout4.esm"])
        self.flags = flags
        self.version = version
        self.next_id = next_id
        self.author = author
        self.description = description
        self.items = []           # list of Group / Record

    def add(self, item):
        self.items.append(item)
        return self

    def records(self):
        for it in self.items:
            if isinstance(it, Group):
                yield from self._walk(it)
            else:
                yield it

    @staticmethod
    def _walk(group):
        for it in group.items:
            if isinstance(it, Group):
                yield from Plugin._walk(it)
            else:
                yield it

    def to_bytes(self):
        import collections
        n = sum(1 for _ in self.records())
        out = bytearray(render_tes4(self.masters, self.flags, self.version, n,
                                    self.next_id, self.author, self.description,
                                    compress=False))
        for it in self.items:
            out += it.to_bytes() if hasattr(it, "to_bytes") else it
        return bytes(out)

    def write(self, path):
        data = self.to_bytes()
        open(path, "wb").write(data)
        return len(data)


# --------------------------------------------------------------------------
# Whole-plugin helpers
# --------------------------------------------------------------------------
def from_bytes(buf, decompress=True):
    """Parse a whole plugin into ``(header: Record, groups: [Group])``.

    Groups keep their raw child bytes; callers that need typed records should
    use :func:`fo4tools.espread.load`.  This exists mainly so
    ``to_bytes(from_bytes(x))`` can be checked.
    """
    from fo4tools import espread as E
    recs = list(E.walk(buf))
    header = recs[0]
    # flatten back into record objects for convenience
    out = []
    for r in recs[1:]:
        out.append(Record(r.type, r.fid, E.subrecords(r.data), flags=r.flags))
    return Record(header.type, header.fid, E.subrecords(header.data),
                  flags=header.flags, form_version=0), out


def to_bytes(header, records, order=None):
    """Build a plugin from a header Record + flat list of Records.

    ``order`` optional list of sigs controlling group emission order.
    """
    import collections
    groups = collections.OrderedDict()
    for r in records:
        groups.setdefault(r.sig, []).append(r)
    out = bytearray(header.to_bytes())
    sigs = order or list(groups)
    for sig in sigs:
        if sig in groups:
            out += render_group(sig, [r.to_bytes() for r in groups[sig]])
    for sig in groups:
        if sig not in sigs:
            out += render_group(sig, [r.to_bytes() for r in groups[sig]])
    return bytes(out)
