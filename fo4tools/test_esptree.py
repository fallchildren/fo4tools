#!/usr/bin/env python3
"""Round-trip test for fo4tools.esptree.

usage: python3 -m fo4tools.test_esptree PLUGIN [PLUGIN ...] [--exact]

For every plugin: parse into a tree, serialize, parse the result again and require that
every record (signature, FormID, flags, header fields, subrecords) and every group (label,
type, stamp, version, nesting) is identical.  With --exact the serialized bytes must also be
identical to the file (true for plugins this toolkit wrote; vanilla / Creation Kit plugins
use a different zlib stream, so they are only compared semantically).
"""
import struct
import sys

from fo4tools import esptree, espwrite as W


def shape(items, depth=0):
    out = []
    for it in items:
        if isinstance(it, W.Group):
            out.append(("G", bytes(it.label), it.group_type, it.stamp, it.version, depth))
            out += shape(it.items, depth + 1)
        else:
            out.append(("R", it.sig, it.fid, it.flags, it.form_version, it.vc, it.unknown,
                        tuple((s.sig, bytes(s.payload)) for s in it.subs), depth))
    return out


def check(path, exact):
    buf = open(path, "rb").read()
    t1 = esptree.parse(buf)
    out = t1.to_bytes()
    t2 = esptree.parse(out)
    a, b = shape(t1.items), shape(t2.items)
    ok = a == b
    hdr_ok = [(s.sig, bytes(s.payload)) for s in t1.header.subs if s.sig != "HEDR"] == \
             [(s.sig, bytes(s.payload)) for s in t2.header.subs if s.sig != "HEDR"]
    rec, grp = t1.counts()
    hedr = [s for s in t2.header.subs if s.sig == "HEDR"][0].payload
    count_ok = struct.unpack("<fII", hedr)[1] == rec + grp
    same = (out == buf)
    msg = "%-34s records=%-6d groups=%-5d tree_equal=%s header_equal=%s hedr_count=%s bytes_identical=%s" % (
        path.split("/")[-1], rec, grp, ok, hdr_ok, count_ok, same)
    print(msg)
    return ok and hdr_ok and count_ok and (same or not exact)


if __name__ == "__main__":
    exact = "--exact" in sys.argv
    paths = [a for a in sys.argv[1:] if not a.startswith("--")]
    bad = sum(0 if check(p, exact) else 1 for p in paths)
    print("RESULT:", "OK" if not bad else "%d FAILED" % bad)
    sys.exit(1 if bad else 0)
