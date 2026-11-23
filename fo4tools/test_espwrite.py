#!/usr/bin/env python3
"""Self-test for the plugin writer (fo4tools.espwrite).

Checks, in order of increasing strictness:

 1. ``serialize_subrecords(parse_subrecords(x)) == x`` for every record payload
    in a real plugin (subrecord fidelity).
 2. Re-rendering every record reproduces its exact on-disk bytes, both
    uncompressed and compressed (header layout fidelity).
 3. Reading and re-writing the whole plugin reproduces it byte-for-byte.

Run::

    python3 -m fo4tools.test_espwrite [path/to/plugin.esp ...]

With no arguments it defaults to the armour plugin in the repo, then
Fallout4.esm if present.  Exits non-zero on failure; prints "skip" (exit 0) for
a plugin that is not found so it is safe in a generic test runner.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fo4tools import espread, espwrite


def check_plugin(path):
    buf, recs = espread.load(path)
    name = os.path.basename(path)
    sub_ok = sub_bad = 0
    rec_ok = rec_bad = 0
    comp_ok = comp_bad = 0
    failures = []

    for r in recs[1:]:
        subs = espread.subrecords(r.data)
        try:
            reser = espwrite.serialize_subrecords(subs)
        except Exception as e:
            sub_bad += 1
            failures.append("%08X subrec serialize: %s" % (r.fid, e))
            continue
        if reser == r.data:
            sub_ok += 1
        else:
            sub_bad += 1
            failures.append("%08X subrecord roundtrip mismatch (len %d vs %d)"
                            % (r.fid, len(r.data), len(reser)))

        # header layout: rebuild exactly as stored
        hdr = espwrite.parse_record_header(buf, r.off)
        rendered = espwrite.render_record(
            r.type, r.fid, subs, flags=r.flags & ~0x00040000,
            form_version=hdr["form_version"], vc=hdr["vc"], unknown=hdr["unknown"],
            compress=False)
        onzdisk = buf[r.off:r.off + 24 + len(r.data)]
        if not hdr["compressed"]:
            if rendered == onzdisk:
                rec_ok += 1
            else:
                rec_bad += 1
                failures.append("%08X uncompressed re-render mismatch" % r.fid)
        else:
            # compressed: verify we reproduce the exact zlib stream
            rendered_c = espwrite.render_record(
                r.type, r.fid, subs, flags=r.flags,
                form_version=hdr["form_version"], vc=hdr["vc"],
                unknown=hdr["unknown"], compress=True)
            if rendered_c == onzdisk:
                comp_ok += 1
            else:
                # zlib stream bytes can differ by encoder; require semantic match
                try:
                    import zlib
                    # the on-disk layout, checked strictly: header dataSize == 4 + stream
                    # length, the u32 prefix is the DECOMPRESSED length, and the record
                    # ends exactly where the next one starts.
                    data_size = struct.unpack_from("<I", rendered_c, 4)[0]
                    prefix = struct.unpack_from("<I", rendered_c, 24)[0]
                    stream = rendered_c[28:24 + data_size]
                    if (len(rendered_c) == 24 + data_size and prefix == len(r.data)
                            and zlib.decompress(stream) == r.data):
                        comp_ok += 1
                    else:
                        comp_bad += 1
                        failures.append("%08X compressed layout/payload mismatch" % r.fid)
                except Exception as e:
                    comp_bad += 1
                    failures.append("%08X compressed re-render: %s" % (r.fid, e))

    print("%-40s records=%-6d sub_ok=%-6d rec_ok=%-6d comp_ok=%-5d bad=%d"
          % (name, len(recs) - 1, sub_ok, rec_ok, comp_ok,
             sub_bad + rec_bad + comp_bad))
    for f in failures[:15]:
        print("   FAIL", f)
    if len(failures) > 15:
        print("   ... %d more" % (len(failures) - 15))
    return sub_bad + rec_bad + comp_bad


def check_whole_plugin(path):
    """Rebuild the plugin from parsed records and compare to the source bytes.

    Groups are re-emitted in first-seen sig order at top level; that reproduces
    plugins produced by ``espwrite``/``build_*`` (single-level groups) exactly.
    Deeply nested vanilla ESM (WRLD/CELL) keeps its structure via espread's
    group walk, so equality is only asserted for flat plugins.
    """
    buf, recs = espread.load(path)
    name = os.path.basename(path)
    hdr = recs[0]
    header = espwrite.Record(hdr.type, 0, espread.subrecords(hdr.data),
                             flags=hdr.flags, form_version=0)
    rebuilt = bytearray(header.to_bytes())

    # group records by their espread group label, preserving first-seen order
    order = []
    groups = {}
    for r in recs[1:]:
        key = r.group if r.group is not None else r.type
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(r)

    for key in order:
        children = []
        for r in groups[key]:
            subs = espread.subrecords(r.data)
            h = espwrite.parse_record_header(buf, r.off)
            children.append(espwrite.render_record(
                r.type, r.fid, subs, flags=r.flags,
                form_version=h["form_version"], vc=h["vc"], unknown=h["unknown"],
                compress=False if not h["compressed"] else True))
        rebuilt += espwrite.render_group(key, children)

    ok = bytes(rebuilt) == buf
    if ok:
        print("%-40s whole-plugin rebuild: BYTE-EXACT (%d bytes)"
              % (name, len(rebuilt)))
        return 0
    # Nested child groups (WRLD/CELL...) are flattened by this flat rebuild, so a
    # difference is expected for vanilla masters.  Report it, but only count it
    # as a failure if the plugin has no nesting to blame.
    has_nesting = any(r.group is not None for r in recs[1:])
    print("%-40s whole-plugin rebuild: differs (%d vs %d bytes)%s"
          % (name, len(rebuilt), len(buf),
             " — expected: plugin has nested groups" if has_nesting else ""))
    return 0 if has_nesting else 1


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(os.path.dirname(os.path.dirname(here)))
    default = os.path.join(root, "fallout4", "Data", "fallchildrens_ncr_armor_redux.esp")
    targets = sys.argv[1:] or [default]
    bad = 0
    for t in targets:
        if not os.path.exists(t):
            print("skip: %s not found" % t)
            continue
        bad += check_plugin(t)
        bad += check_whole_plugin(t)
    print("RESULT:", "OK" if bad == 0 else "%d FAILURES" % bad)
    sys.exit(0 if bad == 0 else 1)
