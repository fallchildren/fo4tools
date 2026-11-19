#!/usr/bin/env python3
"""fo4tools command dispatcher. See the package docstring for an overview."""
import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fo4tools import __version__
from fo4tools import ba2, dx10, espread, graph, nif
from fo4tools import hkx as H
from fo4tools import clip as C


def main(argv=None):
    p = argparse.ArgumentParser(prog="fo4tools", description="Fallout 4 asset toolkit")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    # ---- hkx ----
    hp = sub.add_parser("hkx", help="decompressed animation data")
    hsub = hp.add_subparsers(dest="hcmd", required=True)
    hi = hsub.add_parser("info", help="animation summary")
    hi.add_argument("file")
    hd = hsub.add_parser("dump", help="per-bone per-frame values")
    hd.add_argument("file")
    hd.add_argument("--bone", help="only this bone")
    hd.add_argument("--motion", action="store_true", help="report animated tracks")
    hm = hsub.add_parser("meta", help="TagXML scalar metadata")
    hm.add_argument("path", help="file or directory")
    hm.add_argument("--compare", help="second directory")
    hm.add_argument("--only-diffs", action="store_true")
    hb = hsub.add_parser("bind-fix", help="identity-map transformTrackToBoneIndices")
    hb.add_argument("files", nargs="+")
    hb.add_argument("--check", action="store_true")

    # ---- clip ----
    cp = sub.add_parser("clip", help="clip-level operations")
    csub = cp.add_subparsers(dest="ccmd", required=True)
    cd = csub.add_parser("delta", help="pose diff between two clips")
    cd.add_argument("mod")
    cd.add_argument("vanilla")
    cd.add_argument("--threshold", type=float, default=2.0)
    cr = csub.add_parser("rebase", help="rebase a clip onto a reference pose")
    cr.add_argument("clip")
    cr.add_argument("ref")
    cr.add_argument("out")
    cc = csub.add_parser("copy-cameras", help="take camera bone positions from vanilla")
    cc.add_argument("mod")
    cc.add_argument("vanilla")
    cc.add_argument("out")
    ca = csub.add_parser("apply-delta", help="rebuild as vanilla + mod's pose delta")
    ca.add_argument("vanilla")
    ca.add_argument("mod")
    ca.add_argument("out")
    ca.add_argument("--root", default=",".join(C.DEFAULT_ROOT),
                    help="root-chain bones held from the mod (comma list)")

    # ---- graph ----
    gp = sub.add_parser("graph", help="hkb behaviour graphs")
    gsub = gp.add_subparsers(dest="gcmd", required=True)
    gi = gsub.add_parser("index", help="object index + reverse references")
    gi.add_argument("xml")
    gv = gsub.add_parser("vars", help="variable names")
    gv.add_argument("xml")
    ge = gsub.add_parser("events", help="event names")
    ge.add_argument("xml")

    # ---- ba2 ----
    bp = sub.add_parser("ba2", help="Bethesda archives")
    bsub = bp.add_subparsers(dest="bcmd", required=True)
    bl = bsub.add_parser("list", help="list contents")
    bl.add_argument("archive")
    bl.add_argument("substring", nargs="?", default=None)
    be = bsub.add_parser("extract", help="extract one file")
    be.add_argument("archive")
    be.add_argument("path", help="substring of the archive path")
    be.add_argument("-o", "--out", default=".")
    bx = bsub.add_parser("extract-all", help="extract everything")
    bx.add_argument("archive")
    bx.add_argument("-o", "--out", default=".")
    bx.add_argument("substring", nargs="?", default=None)
    bpk = bsub.add_parser("pack", help="pack a directory tree")
    bpk.add_argument("out", help="output .ba2")
    bpk.add_argument("dir")
    bpk.add_argument("--dx10", action="store_true", help="DX10 texture archive (DDS files)")

    # ---- esp ----
    ep = sub.add_parser("esp", help="plugin records")
    esub = ep.add_subparsers(dest="ecmd", required=True)
    ei = esub.add_parser("info", help="header, masters, record counts")
    ei.add_argument("plugin")
    ed = esub.add_parser("dump", help="list records")
    ed.add_argument("plugin")
    ed.add_argument("--type", help="comma list, e.g. ARMO,WEAP")
    ed.add_argument("--search", help="substring of EDID or FULL name")
    ed.add_argument("--fid", help="exact form id, e.g. 01000F99")

    # ---- order ----
    op = sub.add_parser("order", help="load-order audit")
    osb = op.add_subparsers(dest="ocmd", required=True)
    oa = osb.add_parser("audit")
    oa.add_argument("--plugins", default="Plugins.txt")
    oa.add_argument("--data", default="Data")

    # ---- animtext / clipinfo ----
    at = sub.add_parser("animtext", help="AnimTextData dump")
    at.add_argument("file")
    ci = sub.add_parser("clipinfo", help="behaviour clip info dump")
    ci.add_argument("file")

    # ---- nif ----
    np = sub.add_parser("nif", help="NiStream inspection")
    np.add_argument("file")

    args = p.parse_args(argv)
    try:
        dispatch(args)
    except SystemExit:
        raise
    except Exception as e:
        p.error("%s: %s" % (args.cmd, e))


def dispatch(a):
    if a.cmd == "hkx":
        if a.hcmd == "info":
            anim = H.load_fo4_animation(a.file)
            print(anim.summary())
        elif a.hcmd == "dump":
            anim = H.load_fo4_animation(a.file)
            names = C.bone_names(anim)
            for i, tr in enumerate(anim.tracks):
                nm = names[i] if i < len(names) else "#%d" % i
                if a.bone and a.bone.lower() != nm.lower():
                    continue
                if a.motion and not (tr.rotations and len(tr.rotations) > 1):
                    continue
                print("track %2d %-22s %4d frames" % (i, nm, len(tr.rotations)))
                if not a.bone or a.bone.lower() == nm.lower():
                    for f in range(len(tr.rotations)):
                        r = tr.rotations[f]
                        t = tr.translations[f] if f < len(tr.translations) else None
                        print("   f%-3d rot %8.4f %8.4f %8.4f %8.4f%s" % (
                            f, r[0], r[1], r[2], r[3],
                            "  pos %8.4f %8.4f %8.4f" % tuple(t) if t else ""))
        elif a.hcmd == "meta":
            from fo4tools import hkxmeta
            hkxmeta.run(a.path, a.compare, a.only_diffs)
        elif a.hcmd == "bind-fix":
            for f in a.files:
                msg, n = graph.bind_fix(f, write=not a.check)
                print("%-46s %s" % (os.path.basename(f), msg))
    elif a.cmd == "clip":
        if a.ccmd == "delta":
            m = H.load_fo4_animation(a.mod)
            v = H.load_fo4_animation(a.vanilla)
            print(C.report_delta(m, v, a.threshold))
        elif a.ccmd == "rebase":
            clip = H.load_fo4_animation(a.clip)
            ref = H.load_fo4_animation(a.ref)
            clip, n = C.rebase(clip, ref)
            print("rebased %d tracks (parent-first)" % n)
            H.write_fo4_animation(a.out, clip)
            print("wrote", a.out)
        elif a.ccmd == "copy-cameras":
            m = H.load_fo4_animation(a.mod)
            v = H.load_fo4_animation(a.vanilla)
            m, done = C.copy_cameras(m, v)
            if not done:
                print("SKIP (no camera data)")
            else:
                print("camera positions from vanilla: %s" % ", ".join(done))
                H.write_fo4_animation(a.out, m)
                print("wrote", a.out)
        elif a.ccmd == "apply-delta":
            v = H.load_fo4_animation(a.vanilla)
            m = H.load_fo4_animation(a.mod)
            out, applied, held = C.apply_delta(v, m, tuple(a.root.split(",")))
            print("delta on %d bones, root held from mod on %d" % (applied, held))
            H.write_fo4_animation(a.out, out)
            print("wrote", a.out)
    elif a.cmd == "graph":
        if a.gcmd == "index":
            by, ref = graph.load(a.xml)
            for k in sorted(by, key=lambda s: int(s[1:])):
                el = by[k]
                print("%-6s %-40s %s" % (k, el.get("class"), graph.obj_name(el)))
                for r in sorted(ref.get(k, ())):
                    print("         <- %s" % r)
        elif a.gcmd == "vars":
            print("\n".join(graph.varnames(a.xml) or []))
        elif a.gcmd == "events":
            print("\n".join(graph.eventnames(a.xml) or []))
    elif a.cmd == "ba2":
        if a.bcmd == "list":
            if a.archive.endswith(".ba2") and _is_dx10(a.archive):
                names = dx10.list_names(a.archive)
            else:
                names = ba2.list_names(a.archive)
            for n in names:
                if not a.substring or a.substring.lower() in n.lower():
                    print(n)
        elif a.bcmd == "extract":
            if _is_dx10(a.archive):
                f, records = dx10._read_index(a.archive)
                f.close()
                os.makedirs(a.out, exist_ok=True)
                n = dx10.extract_all(a.archive, a.out, a.path)
                print("extracted %d texture(s) to %s" % (n, a.out))
            else:
                name = ba2.extract_file(a.archive, a.path, a.out)
                print("extracted", name)
        elif a.bcmd == "extract-all":
            if _is_dx10(a.archive):
                n = dx10.extract_all(a.archive, a.out, a.substring)
            else:
                n = ba2.extract_all(a.archive, a.out, a.substring)
            print("extracted %d file(s) to %s" % (n, a.out))
        elif a.bcmd == "pack":
            files = []
            for dirpath, _, names in os.walk(a.dir):
                for n in names:
                    p = os.path.join(dirpath, n)
                    rel = os.path.relpath(p, a.dir).replace(os.sep, "/")
                    files.append((rel, open(p, "rb").read()))
            if a.dx10:
                n = dx10.write_ba2_dx10(a.out, files)
            else:
                n = ba2.write_ba2(a.out, files)
            print("packed %d files -> %s" % (n, a.out))
    elif a.cmd == "esp":
        buf, recs = espread.load(a.plugin)
        if a.ecmd == "info":
            hdr = recs[0]
            print("plugin: %s" % a.plugin)
            for t, d in espread.subrecords(hdr.data):
                if t == "MAST":
                    print("  master: %s" % d.rstrip(b"\0").decode("latin1"))
                elif t == "HEDR":
                    ver, num, nid = struct.unpack("<fII", d)
                    print("  version %.2f  records %d  next id %08X" % (ver, num, nid))
                elif t == "CNAM":
                    print("  author: %s" % d.rstrip(b"\0").decode("latin1"))
            import collections
            print("  types:", dict(collections.Counter(r.type for r in recs[1:])))
        elif a.ecmd == "dump":
            want_types = set(x.strip().upper() for x in (a.type or "").split(",") if x.strip())
            for r in recs[1:]:
                if want_types and r.type not in want_types:
                    continue
                if a.fid and r.fid != int(a.fid, 16):
                    continue
                d = dict(espread.subrecords(r.data))
                edid = d.get("EDID", b"").rstrip(b"\0").decode("latin1")
                full = d.get("FULL", b"").rstrip(b"\0").decode("latin1", "replace")
                if a.search and a.search.lower() not in (edid + full).lower():
                    continue
                print("%08X %-6s %-40s %s" % (r.fid, r.type, edid, full))
    elif a.cmd == "order":
        from fo4tools import loadorder
        loadorder.audit(a.plugins, a.data)
    elif a.cmd == "animtext":
        from fo4tools import animtext as AT
        data = open(a.file, "rb").read()
        if data[:3] == b"V4\n":
            beh, ents, tail = AT.parse_offsets(data)
            print("AnimationOffsets: behaviour %s, %d entries" % (beh, len(ents)))
            for name, path in ents:
                print("   %-40s %s" % (name, path))
        else:
            h, paths = AT.parse_filedata(data)
            print("AnimationFileData: %s, %d paths" % (h, len(paths)))
            for p in paths:
                print("   ", p)
    elif a.cmd == "clipinfo":
        from fo4tools import clipinfo as CI
        n1, blocks, p, n2, _ = CI.parse(open(a.file, "rb").read())
        print("%d behaviour blocks, %d subgraph sections" % (n1, n2))
        for key, path, nrec, s, pe in blocks:
            print("  block %s: %s (%d records)" % (key, path, nrec))
    elif a.cmd == "nif":
        import json
        ni = nif.Nif(a.file)
        print(json.dumps(ni.parse(), indent=1, default=str)[:4000])


def _is_dx10(path):
    try:
        head = open(path, "rb").read(16)
        return head[:4] == b"BTDX" and head[8:12] == b"DX10"
    except OSError:
        return False


if __name__ == "__main__":
    main()
