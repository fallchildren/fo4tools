#!/usr/bin/env python3
"""Self-test for the object-template decoder.

Verifies that every OBTS record in Fallout4.esm parses and round-trips
byte-exactly.  Run:

    python3 -m fo4tools.test_objecttemplate [path/to/Fallout4.esm]

Exits non-zero on any failure.  If the ESM is not present it exits 0 with a
"skipped" message so it is safe to wire into a generic test runner.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fo4tools import espread, objecttemplate as OT


def run(path):
    if not os.path.exists(path):
        print("skip: %s not found" % path)
        return 0
    buf, recs = espread.load(path)
    types = {r.fid: r.type for r in recs[1:]}
    total = ok = rt = 0
    failures = []
    for r in recs[1:]:
        for sig, payload in espread.subrecords(r.data):
            if sig != "OBTS":
                continue
            total += 1
            try:
                t = OT.parse_obts(payload)
            except ValueError as e:
                failures.append("%08X parse: %s" % (r.fid, e))
                continue
            ok += 1
            # every include must resolve to an OMOD, every keyword to KYWD
            bad = [hex(i.mod) for i in t.includes if types.get(i.mod) != "OMOD"]
            bad += [hex(k) for k in t.keywords if k and types.get(k) != "KYWD"]
            if bad:
                failures.append("%08X refs: %s" % (r.fid, bad))
            if OT.build_obts(t) == payload:
                rt += 1
            else:
                failures.append("%08X roundtrip mismatch (len %d vs %d)"
                                % (r.fid, len(payload), len(OT.build_obts(t))))
    print("OBTS records: %d   parsed: %d   exact round-trip: %d" % (total, ok, rt))
    for f in failures[:20]:
        print("  FAIL", f)
    if len(failures) > 20:
        print("  ... %d more" % (len(failures) - 20))
    return 0 if (total and ok == total and rt == total and not failures) else 1


if __name__ == "__main__":
    default = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "..", "..", "fallout4", "Data", "Fallout4.esm")
    sys.exit(run(sys.argv[1] if len(sys.argv) > 1 else default))
