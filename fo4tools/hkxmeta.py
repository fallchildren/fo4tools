"""Summarize hkx TagXML metadata for unpacked files, and diff two sets by key.

Keys are the unpacked filenames (which encode the original subdir as "sub_name").
"""
import os, re

TAGS = ["type", "numFrames", "numberOfTransformTracks", "numberOfFloatTracks",
        "duration", "frameDuration", "blockDuration", "originalSkeletonName"]


def summarize(path):
    """Pull the handful of scalar params we care about out of one TagXML."""
    with open(path, "r", errors="replace") as f:
        txt = f.read()
    out = {}
    for t in TAGS:
        m = re.search(r'name="%s">([^<]*)' % t, txt)
        if m:
            out[t] = m.group(1)
    m = re.search(r'name="transformTrackToBoneIndices"\s+numelements="(\d+)">(\s*[\d\s]*)', txt)
    if m:
        idx = [int(x) for x in m.group(2).split()]
        out["tracks"] = m.group(1)
        out["boneMap"] = "identity" if idx == list(range(len(idx))) else "custom"
        out["maxBone"] = str(max(idx)) if idx else "-"
    ann = re.findall(r'<hkparam name="text">([^<]*)</hkparam>', txt)
    if ann:
        out["annotations"] = ",".join(ann)
    m = re.search(r'name="data" numelements="(\d+)"', txt)
    if m:
        out["dataWords"] = m.group(1)
    return out


def dump(d):
    files = sorted(f for f in os.listdir(d) if f.endswith(".xml"))
    return {os.path.splitext(f)[0].lower(): summarize(os.path.join(d, f)) for f in files}


def fmt(v):
    def sh(x):
        try:
            return "%.4g" % float(x)
        except Exception:
            return x
    return " ".join([
        v.get("type", "?").replace("HK_", ""),
        v.get("numFrames", "?"),
        v.get("numberOfTransformTracks", "?"),
        v.get("numberOfFloatTracks", "?"),
        sh(v.get("duration", "?")),
        sh(v.get("frameDuration", "?")),
        v.get("boneMap", "?"),
        v.get("maxBone", "?"),
    ])


def run(path, compare=None, only_diffs=False):
    """CLI entry: dump one file/dir, or compare two dirs."""
    if not compare:
        if os.path.isdir(path):
            for k, v in sorted(dump(path).items()):
                print("%-36s %s" % (k, fmt(v)))
        else:
            for k, v in summarize(path).items():
                print("%-36s %s" % (k, fmt(v)))
        return
    a, b = dump(path), dump(compare)
    keys = sorted(set(a) | set(b))
    for k in keys:
        va, vb = a.get(k), b.get(k)
        if va is None:
            print("%-36s ONLY-IN-B  %s" % (k, fmt(vb))); continue
        if vb is None:
            print("%-36s ONLY-IN-A  %s" % (k, fmt(va))); continue
        same = fmt(va) == fmt(vb)
        ann_same = va.get("annotations") == vb.get("annotations")
        if same and ann_same:
            if not only_diffs:
                print("%-36s SAME       %s" % (k, fmt(va)))
        else:
            print("%-36s %-10s A=%s | B=%s" % (k, "DIFF" if not same else "ANN-DIFF", fmt(va), fmt(vb)))
    print("compared %d keys (A=%d B=%d)" % (len(keys), len(a), len(b)))
