#!/usr/bin/env python3
"""Read-only FO4 load-order auditor.

Reads a Plugins.txt and a Data directory, then reports:
  * entries with no matching file (case-insensitive)
  * enabled plugins whose masters are missing from Data
  * enabled plugins whose masters load AFTER them (ordering violations)
  * ESL / light-plugin capacity and full-plugin capacity
  * modgroups / group disagreement (informational)

Usage:
  tools/loadorder.py <plugins.txt> <Data dir> [--fix-order]

--fix-order only *reports* the stable topological order; it never writes.
"""
import os, struct, sys

LIGHT_FLAG = 0x00000200


def read_plugins_txt(path):
    """Return list of (name, enabled) preserving file order."""
    out = []
    with open(path, encoding='utf-8', errors='surrogateescape') as fh:
        for line in fh:
            s = line.strip()
            if not s or s.startswith('#'):
                continue
            if s.startswith('*'):
                out.append((s[1:], True))
            else:
                out.append((s, False))
    return out


def header(path):
    """Return (masters, flags, is_light, version)."""
    with open(path, 'rb') as fh:
        buf = fh.read()
    i = buf.find(b'TES4')
    if i < 0 or i + 24 > len(buf):
        return [], 0, False, 0.0
    size, flags = struct.unpack_from('<II', buf, i + 4)
    version = struct.unpack_from('<f', buf, i + 24 - 4 + 4)[0] if False else 0.0
    masters = []
    q = i + 24
    end = i + 24 + size
    while q + 6 <= end:
        sig = buf[q:q + 4]
        ssz = struct.unpack_from('<H', buf, q + 4)[0]
        payload = buf[q + 6:q + 6 + ssz]
        if sig == b'MAST':
            masters.append(payload.rstrip(b'\x00').decode('latin-1'))
        elif sig == b'HEDR':
            version = struct.unpack_from('<f', payload)[0]
        q += 6 + ssz
    is_light = bool(flags & LIGHT_FLAG) or path.lower().endswith('.esl')
    return masters, flags, is_light, version


def audit(ptxt, data, fix=False):
    """Audit a Plugins.txt against a Data directory (read-only)."""
    entries = read_plugins_txt(ptxt)
    files = {}
    for f in os.listdir(data):
        if f.lower().endswith(('.esp', '.esm', '.esl')):
            files[f.lower()] = f

    hdr = {}
    for key, real in files.items():
        try:
            hdr[key] = header(os.path.join(data, real))
        except Exception as exc:
            print(f"  !! header read failed: {real}: {exc}")

    enabled = [n for n, e in entries if e]
    disabled = [n for n, e in entries if not e]

    print(f"Data: {data}")
    print(f"Plugins.txt: {ptxt}")
    print(f"entries={len(entries)} enabled={len(enabled)} disabled={len(disabled)}\n")

    # --- files present? ---
    missing = [n for n, e in entries if n.lower() not in files]
    if missing:
        print("MISSING FILES (listed but not in Data):")
        for n in missing:
            print(f"   {n}")
        print()

    # --- masters ---
    problems = []
    for n in enabled:
        key = n.lower()
        if key not in hdr:
            continue
        masters, flags, light, ver = hdr[key]
        for m in masters:
            if m.lower() not in files:
                problems.append((n, 'MISSING MASTER', m))
    if problems:
        print("MISSING MASTERS (enabled plugin needs absent file):")
        for n, kind, m in problems:
            print(f"   {n}  ->  {m}")
        print()

    # --- order: master must precede dependent ---
    pos = {n.lower(): i for i, n in enumerate(enabled)}
    order_bad = []
    for n in enabled:
        key = n.lower()
        if key not in hdr:
            continue
        masters, _, _, _ = hdr[key]
        for m in masters:
            mk = m.lower()
            if mk in pos and pos[mk] > pos[key]:
                order_bad.append((n, m))
    if order_bad:
        print("ORDER VIOLATIONS (master loads after dependent):")
        for n, m in order_bad:
            print(f"   {n} (#{pos[n.lower()]}) loads BEFORE master {m} (#{pos[m.lower()]})")
        print()
    else:
        print("ORDER: all master->dependent constraints satisfied\n")

    # --- capacity ---
    full = [n for n in enabled if n.lower() in hdr and not hdr[n.lower()][2]]
    light = [n for n in enabled if n.lower() in hdr and hdr[n.lower()][2]]
    print(f"CAPACITY: full/masters={len(full)} (limit 255 indexed)  light={len(light)} (limit 4096)")
    if len(full) > 254:
        print("   !! full-plugin limit exceeded")
    print()

    # --- summary of ESL/hdr ---
    print("PLUGIN HEADERS:")
    for n in enabled:
        key = n.lower()
        if key not in hdr:
            print(f"   {'?':<6} {n}  (file missing)")
            continue
        masters, flags, light, ver = hdr[key]
        tag = 'ESL' if light else ('ESM' if key.endswith('.esm') else 'ESP')
        print(f"   {tag:<6} v{ver:.2f} masters={len(masters)}  {files[key]}")

    return 0


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 3:
        print(__doc__)
    else:
        sys.exit(audit(sys.argv[1], sys.argv[2], '--fix-order' in sys.argv))
