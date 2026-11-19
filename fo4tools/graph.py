"""hkb behaviour-graph (TagXML) helpers: object index, references, variables,
events, and the transformTrackToBoneIndices identity-map repair."""
import xml.etree.ElementTree as ET
import re
import collections


def load(path):
    """-> (by_name: dict '#id' -> Element, refs: dict '#id' -> set of '#referrer')"""
    root = ET.parse(path).getroot()
    by = {}
    for el in root.iter('hkobject'):
        n = el.get('name')
        if n and n.startswith('#') and el.get('class'):
            by[n] = el
    ref = collections.defaultdict(set)
    for k, el in by.items():
        for sub in el.iter():
            if sub.text:
                for r in set(re.findall(r'#\d+', sub.text)):
                    if r != k and r in by:
                        ref[r].add(k)
    return by, ref


def param(el, name):
    for c in el:
        if c.tag == 'hkparam' and c.get('name') == name:
            return (c.text or '').strip()
    return None


def obj_name(el):
    return param(el, 'name') or ''


def string_list(path, which):
    """Read hkbBehaviorGraphStringData.<which> (variableNames / eventNames / ...)"""
    for el in ET.parse(path).getroot().iter('hkobject'):
        if el.get('class') == 'hkbBehaviorGraphStringData':
            for c in el:
                if c.get('name') == which:
                    return [x.text for x in c.iter('hkcstring')]
    return None


def varnames(path):
    return string_list(path, 'variableNames')


def eventnames(path):
    return string_list(path, 'eventNames')


# --- binding repair (the old fixbind.py) --------------------------------------

def _num_tracks(txt):
    m = re.search(r'name="numberOfTransformTracks">(\d+)', txt)
    return int(m.group(1)) if m else None


def _binding_state(txt):
    m = re.search(r'name="transformTrackToBoneIndices"\s+numelements="(\d+)"\s*(/?)>', txt)
    if not m:
        return None, None
    return int(m.group(1)), (m.group(2) == "/")


def bind_fix(path, write=True):
    """Rewrite an empty transformTrackToBoneIndices into the identity map.
    Returns (status message, track count or None)."""
    txt = open(path, encoding='utf-8', errors='surrogateescape').read()
    n = _num_tracks(txt)
    have, selfclosing = _binding_state(txt)
    if n is None:
        return "skip (no track count)", None
    if have is None:
        return "skip (no binding param)", None
    if have != 0:
        return "already mapped (%d)" % have, None
    if not selfclosing:
        return "not self-closing; manual review", None
    lines = []
    for i in range(0, n, 24):
        lines.append(" ".join(str(j) for j in range(i, min(i + 24, n))))
    body = "\n".join(lines)
    new = ('<hkparam name="transformTrackToBoneIndices" numelements="%d">\n%s</hkparam>' % (n, body))
    old = '<hkparam name="transformTrackToBoneIndices" numelements="0"/>'
    if write:
        txt2 = txt.replace(old, new, 1)
        if txt2 == txt:
            return "REPLACE FAILED", None
        open(path, 'w', encoding='utf-8', errors='surrogateescape').write(txt2)
        after, _ = _binding_state(txt2)
        return "patched -> %d entries" % (after or -1), n
    return "would patch -> %d entries" % n, n
