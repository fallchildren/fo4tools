"""Clip-level operations on decompressed FO4 animations.

All functions work on hkx.AnimationData. Bone names and parents are taken from
the animation's own skeleton when present; otherwise the built-in FO4 95-bone
rig tables are used as fallback.
"""
import math
from . import hkx

# --- FO4 human rig fallback (when the file carries no skeleton) ---------------
FO4_BONES = ['Root', 'COM', 'Pelvis', 'LLeg_Thigh', 'LLeg_Calf', 'LLeg_Foot',
    'RLeg_Thigh', 'RLeg_Calf', 'RLeg_Foot', 'Spine1', 'Spine2', 'Chest', 'Neck',
    'Head', 'LArm_Collarbone', 'LArm_UpperArm', 'LArm_ForeArm1', 'LArm_ForeArm2',
    'LArm_ForeArm3', 'LArm_Hand', 'RArm_Collarbone', 'RArm_UpperArm',
    'RArm_ForeArm1', 'RArm_ForeArm2', 'RArm_ForeArm3', 'PipboyBone', 'RArm_Hand',
    'WeaponLeft', 'Weapon', 'WeaponBolt', 'WeaponExtra1', 'WeaponExtra2',
    'WeaponExtra3', 'WeaponMagazine', 'WeaponMagazineChild1',
    'WeaponMagazineChild2', 'WeaponMagazineChild3', 'WeaponMagazineChild4',
    'WeaponMagazineChild5', 'WeaponOptics1', 'WeaponOptics2', 'WeaponTrigger',
    'LArm_UpperTwist1', 'LArm_UpperTwist2', 'RArm_UpperTwist1',
    'RArm_UpperTwist2', 'LLeg_Toe1', 'RLeg_Toe1', 'LArm_Finger11',
    'LArm_Finger12', 'LArm_Finger13', 'LArm_Finger21', 'LArm_Finger22',
    'LArm_Finger23', 'LArm_Finger31', 'LArm_Finger32', 'LArm_Finger33',
    'LArm_Finger41', 'LArm_Finger42', 'LArm_Finger43', 'LArm_Finger51',
    'LArm_Finger52', 'LArm_Finger53', 'RArm_Finger11', 'RArm_Finger12',
    'RArm_Finger13', 'RArm_Finger21', 'RArm_Finger22', 'RArm_Finger23',
    'RArm_Finger31', 'RArm_Finger32', 'RArm_Finger33', 'RArm_Finger41',
    'RArm_Finger42', 'RArm_Finger43', 'RArm_Finger51', 'RArm_Finger52',
    'RArm_Finger53', 'Camera', 'Camera Control', 'AnimObjectA', 'AnimObjectB',
    'WeaponIKTargetL', 'WeaponIKTargetR', 'WeaponIKTargetLMirror',
    'WeaponIKTargetRMirror', 'AnimObjectL1', 'AnimObjectL2', 'AnimObjectL3',
    'AnimObjectR1', 'AnimObjectR2', 'AnimObjectR3', 'L_RibHelper',
    'R_RibHelper', 'CamTarget']

FO4_PARENTS = [-1, 0, 1, 2, 3, 4, 2, 6, 7, 1, 9, 10, 11, 12, 11, 14, 15, 16,
    17, 18, 11, 20, 21, 22, 23, 18, 24, 19, 26, 28, 28, 28, 28, 28, 33, 33, 33,
    33, 33, 28, 28, 28, 15, 42, 21, 44, 5, 8, 19, 48, 49, 19, 51, 52, 19, 54,
    55, 19, 57, 58, 19, 60, 61, 26, 63, 64, 26, 66, 67, 26, 69, 70, 26, 72, 73,
    26, 75, 76, 0, 0, 0, 0, 28, 28, 28, 28, 19, 19, 19, 26, 26, 26, 11, 11, 0]

# --- helpers ------------------------------------------------------------------
def bone_names(anim):
    """Bone name per track, from the file's skeleton or the FO4 fallback."""
    if anim.skeleton and anim.skeleton.bones:
        return anim.skeleton.bones
    if anim.bone_names and any(anim.bone_names):
        return anim.bone_names
    return FO4_BONES

def parents(anim):
    if anim.skeleton and anim.skeleton.parents:
        return anim.skeleton.parents
    return FO4_PARENTS

def qinv(q):
    n = sum(x * x for x in q) or 1.0
    return [-q[0] / n, -q[1] / n, -q[2] / n, q[3] / n]

def qmul(a, b):
    return [a[3] * b[0] + a[0] * b[3] + a[1] * b[2] - a[2] * b[1],
            a[3] * b[1] + a[1] * b[3] + a[2] * b[0] - a[0] * b[2],
            a[3] * b[2] + a[2] * b[3] + a[0] * b[1] - a[1] * b[0],
            a[3] * b[3] - a[0] * b[0] - a[1] * b[1] - a[2] * b[2]]

def norm(q):
    n = math.sqrt(sum(x * x for x in q)) or 1.0
    return [x / n for x in q]

def deg(q):
    return math.degrees(2 * math.acos(min(1.0, abs(q[3]))))

# --- operations ---------------------------------------------------------------
def delta(a, b):
    """Per-bone pose delta at frame 0: mod x inv(vanilla). -> dict track->quat"""
    out = {}
    for k in range(min(a.num_tracks, b.num_tracks)):
        if a.tracks[k].rotations and b.tracks[k].rotations:
            out[k] = qmul(a.tracks[k].rotations[0], qinv(b.tracks[k].rotations[0]))
    return out

def report_delta(a, b, threshold=2.0):
    """Human-readable diff of two clips (see the old delta.py)."""
    names = bone_names(a)
    lines = ["mod: %d fr / %d tr    vanilla: %d fr / %d tr"
             % (a.num_frames, a.num_tracks, b.num_frames, b.num_tracks)]
    diffs = []
    for k, d in delta(a, b).items():
        if deg(d) > threshold:
            diffs.append((names[k] if k < len(names) else str(k), deg(d)))
    lines.append("bones differing >%.1f deg: %d of %d"
                 % (threshold, len(diffs), min(a.num_tracks, b.num_tracks)))
    for n, x in sorted(diffs, key=lambda p: -p[1]):
        lines.append("   %-24s %.1f deg" % (n, x))
    if not diffs:
        lines.append("   (identical pose data)")
    return "\n".join(lines)

def rebase(clip, ref):
    """Rebase a clip so its frame 0 equals the reference pose, parent-first
    (the old chargefix.py). Mutates and returns clip."""
    names = bone_names(clip)
    par = parents(clip)
    newlocals = {}
    n = 0
    for k in range(clip.num_tracks):
        tr = clip.tracks[k]
        if not tr.rotations:
            continue
        if k >= ref.num_tracks or not ref.tracks[k].rotations:
            continue
        p = par[k] if k < len(par) else -1
        p_new = world_from(clip, p, 0, par, newlocals) if p >= 0 else [0, 0, 0, 1.0]
        p_ref = world_from(ref, p, 0, par) if p >= 0 else [0, 0, 0, 1.0]
        old0 = tr.rotations[0]
        pre = qmul(qmul(qinv(p_new), p_ref),
                   qmul(ref.tracks[k].rotations[0], qinv(old0)))
        tr.rotations = [norm(qmul(pre, q)) for q in tr.rotations]
        newlocals[k] = tr.rotations[0]
        n += 1
    return clip, n

def world_from(anim, k, fr, par, override=None):
    """World orientation of track k at frame fr (parent chain)."""
    q = [0, 0, 0, 1.0]
    chain = []
    while k >= 0:
        chain.append(k)
        k = par[k] if k < len(par) else -1
    for k in reversed(chain):
        if override and k in override:
            r = override[k]
        else:
            tr = anim.tracks[k]
            r = tr.rotations[fr] if tr.rotations else [0, 0, 0, 1.0]
        q = qmul(q, r)
    return norm(q)

CAMERA_BONES = ("Camera", "CamTarget", "AnimObjectA", "AnimObjectB")

def copy_cameras(mod, vanilla):
    """Give a mod clip the vanilla camera bone positions (the old campos.py).
    Mutates and returns mod."""
    names = bone_names(mod)
    done = []
    for i, tr in enumerate(mod.tracks):
        if i >= len(names) or names[i] not in CAMERA_BONES:
            continue
        if i >= vanilla.num_tracks or not vanilla.tracks[i].translations:
            continue
        pos = list(vanilla.tracks[i].translations[0])
        tr.translations = [list(pos) for _ in tr.translations]
        done.append(names[i])
    return mod, done

DEFAULT_ROOT = ("COM", "Pelvis", "Spine1")

def apply_delta(vanilla, mod, root=DEFAULT_ROOT):
    """Rebuild a clip as vanilla + the mod's pose delta, holding the root chain
    from the mod (the old rebuild3.py). Mutates and returns vanilla."""
    names = bone_names(vanilla)
    d = delta(mod, vanilla)
    rootk = {names.index(n) for n in root if n in names}
    applied = held = 0
    for k, tr in enumerate(vanilla.tracks):
        if k in rootk and mod.tracks[k].rotations:
            tr.rotations = [list(mod.tracks[k].rotations[0]) for _ in tr.rotations]
            if mod.tracks[k].translations:
                tr.translations = [list(mod.tracks[k].translations[0]) for _ in tr.translations]
            held += 1
            continue
        if k not in d or not tr.rotations:
            continue
        tr.rotations = [norm(qmul(d[k], q)) for q in tr.rotations]
        applied += 1
    return vanilla, applied, held
