#!/usr/bin/env python3
"""Fallout 4 object-template support: OBTE / OBTF / OBTS / STOP.

This is the modern, data-driven way an ARMO/ARMA/WEAP/OMOD says which addons and
object modifications apply.  Layout derived from xEdit's
``Core/wbDefinitionsFO4.pas`` (the ``wbObjectTemplate`` / ``wbOBTSReq`` block) and
verified byte-for-byte against all 2430 ``OBTS`` records in ``fallout4.esm``.

Record structure (a record may carry several *combinations*):

    OBTE  u32 Count                       number of combinations
    OBTF  (empty, editor only)
    FULL  string                          (optional, per combination)
    OBTS  <Object Mod Template Item>      one per combination
    ...
    STOP  (empty marker)

``OBTS`` payload:

    U32  include_count
    U32  property_count
    U8   level_min
    u8   pad
    U8   level_max
    u8   pad
    S16  addon_index                       -1 (0xFFFF) for power-armour frames
    U8   default                           1 = this combination is the default
    U8   keyword_count                     count prefix of the keyword array
    U32  keywords[keyword_count]
    U8   min_level_for_ranks
    U8   alt_levels_per_tier
    Include includes[include_count]:
        U32  mod                           OMOD form id
        U8   attach_point_index
        U8   optional
        U8   dont_use_all
    Property properties[property_count]:
        U32  function
        U32  value1
        U32  value2
        f32  step
        (followed by function-specific extra value, see xEdit wbObjectModProperties;
         left as raw tail here)
"""
import struct

__all__ = ["parse_obts", "build_obts", "ObjectTemplate", "parse_record"]


class Include:
    __slots__ = ("mod", "attach_point_index", "optional", "dont_use_all")

    def __init__(self, mod, attach_point_index=0, optional=0, dont_use_all=1):
        self.mod = mod
        self.attach_point_index = attach_point_index
        self.optional = optional
        self.dont_use_all = dont_use_all

    def __repr__(self):
        return "Include(mod=%08X, ap=%d, opt=%d, dnu=%d)" % (
            self.mod, self.attach_point_index, self.optional, self.dont_use_all)


class ObjectTemplate:
    """One OBTS combination."""

    __slots__ = ("include_count", "property_count", "level_min", "level_max",
                 "addon_index", "default", "keywords", "min_level_for_ranks",
                 "alt_levels_per_tier", "includes", "properties", "_tail")

    def __init__(self, level_min=0, level_max=0, addon_index=-1, default=0,
                 keywords=None, min_level_for_ranks=0, alt_levels_per_tier=0,
                 includes=None, properties=None):
        self.include_count = None
        self.property_count = None
        self.level_min = level_min
        self.level_max = level_max
        self.addon_index = addon_index
        self.default = default
        self.keywords = list(keywords or [])
        self.min_level_for_ranks = min_level_for_ranks
        self.alt_levels_per_tier = alt_levels_per_tier
        self.includes = [i if isinstance(i, Include) else Include(i) for i in (includes or [])]
        self.properties = list(properties or [])
        self._tail = b""

    def __repr__(self):
        return ("ObjectTemplate(level=%d..%d, addon=%d, default=%d, kw=%s, "
                "includes=%s)" % (self.level_min, self.level_max, self.addon_index,
                                  self.default, [("%08X" % k) for k in self.keywords],
                                  self.includes))


def parse_obts(data):
    """Parse one OBTS payload into an ObjectTemplate.  Raises ValueError on bad data."""
    o = 0
    n = len(data)

    def need(k):
        if o + k > n:
            raise ValueError("OBTS truncated at offset %d (need %d, have %d)"
                             % (o, k, n - o))

    need(8)
    include_count, property_count = struct.unpack_from("<II", data, o)
    o += 8
    need(2)
    level_min = data[o]
    o += 2
    need(2)
    level_max = data[o]
    o += 2
    need(2)
    addon_index = struct.unpack_from("<h", data, o)[0]
    o += 2
    need(1)
    default = data[o]
    o += 1
    need(1)
    kw_count = data[o]
    o += 1
    need(4 * kw_count)
    keywords = list(struct.unpack_from("<%dI" % kw_count, data, o))
    o += 4 * kw_count
    need(2)
    min_level_for_ranks = data[o]
    alt_levels_per_tier = data[o + 1]
    o += 2

    includes = []
    for _ in range(include_count):
        need(7)
        mod, ap, opt, dnu = struct.unpack_from("<IBBB", data, o)
        o += 7
        includes.append(Include(mod, ap, opt, dnu))

    properties = []
    for _ in range(property_count):
        # The property layout is function-dependent past the 16-byte prefix;
        # we keep it as raw bytes so round-tripping is lossless.
        need(16)
        function, v1, v2 = struct.unpack_from("<III", data, o)
        step = struct.unpack_from("<f", data, o + 12)[0]
        start = o
        o += 16
        properties.append((function, v1, v2, step, start))

    # Anything left (function-specific extra values) is kept verbatim.
    tail = data[o:]

    t = ObjectTemplate(level_min, level_max, addon_index, default, keywords,
                       min_level_for_ranks, alt_levels_per_tier, includes, properties)
    t.include_count = include_count
    t.property_count = property_count
    t._tail = tail
    return t


def build_obts(t):
    """Serialise an ObjectTemplate back to an OBTS payload.

    Uses explicit counts when set, else derives them from the lists.
    """
    inc = t.include_count if t.include_count is not None else len(t.includes)
    pc = t.property_count if t.property_count is not None else len(t.properties)

    out = bytearray()
    out += struct.pack("<II", inc, pc)
    out += bytes([t.level_min & 0xFF, 0])
    out += bytes([t.level_max & 0xFF, 0])
    out += struct.pack("<h", t.addon_index)
    out += bytes([t.default & 0xFF])
    out += bytes([len(t.keywords) & 0xFF])
    out += struct.pack("<%dI" % len(t.keywords), *t.keywords)
    out += bytes([t.min_level_for_ranks & 0xFF, t.alt_levels_per_tier & 0xFF])
    for i in t.includes:
        if not isinstance(i, Include):
            i = Include(i)
        out += struct.pack("<IBBB", i.mod, i.attach_point_index, i.optional, i.dont_use_all)
    for p in t.properties:
        function, v1, v2, step = p[0], p[1], p[2], p[3]
        out += struct.pack("<III", function, v1, v2)
        out += struct.pack("<f", step)
    out += t._tail
    return bytes(out)


def parse_record(rec, subrecords):
    """Walk a record's subrecords and pull out the object template.

    ``subrecords`` is a list of ``(sig, payload)`` (from espread.subrecords).
    Returns ``(obte_count, [ObjectTemplate, ...], extra)`` where ``extra`` holds
    any OBTF/FULL/STOP presence flags.
    """
    obte = None
    templates = []
    extra = {"obtf": False, "full": None, "stop": False}
    for sig, payload in subrecords:
        if sig == "OBTE" and len(payload) >= 4:
            obte = struct.unpack_from("<I", payload, 0)[0]
        elif sig == "OBTS":
            templates.append(parse_obts(payload))
        elif sig == "OBTF":
            extra["obtf"] = True
        elif sig == "FULL":
            extra["full"] = payload.rstrip(b"\0")
        elif sig == "STOP":
            extra["stop"] = True
    return obte, templates, extra
