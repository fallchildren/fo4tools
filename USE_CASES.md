# fo4tools — use cases

A task-oriented companion to the [README](README.md). Everything here is written
backwards from a real problem: *"the armour renders with no mesh"*, *"which
plugin wins this record?"*, *"why did my plugin hang the load?"*. Each case shows
the commands, the actual output, and what it means.

The running example is a real mod: an NCR Ranger armour merge that pulls records
from two source plugins into one, splits a helmet's tint from its light slot, and
absorbs a third mod as a master. It hit almost every problem below.

```
fo4tools/bin/fo4tools ...          # no install needed, works from any directory
```

> Scope: this book covers plugins (`esp`) and archives (`ba2`), because that is
> where the sharp edges are. `fo4tools` also reads and writes animation data —
> see `hkx`, `clip`, `graph` in the README.

---

## 1. First contact: what is in this plugin at all?

```sh
fo4tools esp info Data/myplugin.esp
```

```
plugin: Data/fallchildrens_ncr_armor_redux.esp
  version 0.95  records 166  next id 02000940
  author: fallchildrens_ncr_armor_redux
  master: Fallout4.esm
  master: Tactical Night Vision.esp
  types: {'KYWD': 13, 'ARMO': 2, 'LIGH': 14, 'MISC': 14, 'IMAD': 3,
          'ADDN': 14, 'ARMA': 2, 'COBJ': 38, 'OMOD': 38, 'MSWP': 24,
          'LENS': 3, 'CONT': 1}
```

Three things to read here, in order:

* **masters** — what this plugin depends on. If a master is missing or loads
  *after* this plugin, nothing loads.
* **next id** — the high byte tells you where this plugin's own records live.
  `01…` = 1 master, `02…` = 2 masters. That is not cosmetic; see §9.
* **types** — a plugin full of `OMOD`/`COBJ`/`MSWP` is an armour workbench mod.
  A plugin with `WEAP`/`LVLI`/`OTFT` is about equipment distribution.

## 2. Find the records you care about

`dump` prints `formID TYPE EDID FULL-name`. Filters combine.

```sh
fo4tools esp dump Data/myplugin.esp --type OMOD --search Light
```

```
0200088A OMOD   omod_NVRHFlashlight_RedLight      Flashlight Red
02000891 OMOD   omod_NVRHFlashlight_BlueLight     Flashlight Blue
020008A1 OMOD   omod_NVRHFlashlight_BrightLight   Flashlight Bright
...
```

* `--type LIST` — comma separated, e.g. `ARMO,ARMA,OMOD`
* `--search TEXT` — case-insensitive substring of EDID **or** the display name.
  Search `helmet` and you find records whose EDID says `Armor_…` but whose
  in-game name says `Veteran Ranger Helmet`.
* `--fid HEX` — exact form id when you already know it

This is the single most-used command. When a user says *"the flashlight mod
doesn't work"*, this is how you find the four records involved in ten seconds.

## 3. Read one record's guts

`dump` shows names. `rec` shows everything, which is what you actually need.

```sh
fo4tools esp rec Data/myplugin.esp 020008A1
```

```
OMOD 020008A1  edid=omod_NVRHFlashlight_BrightLight  flags=00000000  size=259
  EDID    32  6f6d6f64...  "omod_NVRHFlashlight_BrightLight"
  FULL    18  466c6173...  "Flashlight Bright"
  DESC    52  41747461...  "Attaches the bright flashlight to the ranger helmet"
  MODL    53  41726d6f...  "Armor\NVRL\FLASHLIGHT\FlashlightAddOnNode_Bright.nif"
  MODT    20  04000000...
  DATA    28  00000000...0000000000
        -> 00000000(?), 52410000(?), 02000900(KYWD), 00000000(?)
  MNAM     4  01090002
        -> 02000901(KYWD)
  LNAM     4  97080001
        -> 02000897(MISC)
```

Reading it:

* `MODL` — the mesh this mod attaches. **Type-dependent** (§11).
* `DATA` — the OMOD's settings: include/property counts, form type, attach point.
* `MNAM` — the keyword of the slot it lives in.
* `LNAM` — the loose-mod item (`MISC`) it corresponds to in the world.
* the `->` lines resolve any short payload's leading FormIDs to record types, so
  you can see at a glance that `MNAM` really is a `KYWD` and not a typo'd fid.

`--hex` suppresses the ASCII column; `--max N` truncates long payloads.

## 4. "The armour is invisible" — check the addon link first

Classic symptom, and almost always this:

```sh
fo4tools esp rec Data/myplugin.esp 020008B1 | grep -A1 '^  MODL'
```

```
  MODL     4  00080002
        -> 02000800(ARMA)
```

On an `ARMO`, `MODL` is a **list of `ARMA` FormIDs**, and each `ARMA` carries the
actual NIF paths (`MOD2`/`MOD3`). If that fid does not resolve to an `ARMA`, the
armour renders with no mesh and no error anywhere:

```sh
fo4tools esp rec Data/myplugin.esp 02000800 | grep -E 'MOD2|MOD3'
```

```
  MOD2    37  ...  "Erynture\ReduxRanger\ReduxHelmet.nif"
  MOD3    38  ...  "Erynture\ReduxRanger\ReduxHelmetF.nif"
```

If `rec` prints `no record 02000800 in …`, you have a dangling addon link — stop
looking at meshes, fix the FormID.

## 5. What does this armour apply by default?

Object templates (`OBTE`/`OBTS`) are how a spawned item arrives pre-modded, and
they are unreadable by eye.

```sh
fo4tools esp template Data/myplugin.esp --fid 020008B1
```

```
020008B1 ARMO   0ArmorReduxHelmet                        Veteran Ranger Helmet
    OBTE count=1  OBTS combinations=1
      [0] levels 0..0 addon=-1 default=1
           include: mod=0200081B(OMOD) ap=0 optional=0 dontuseall=1
           include: mod=020008A1(OMOD) ap=0 optional=0 dontuseall=1
```

* **`default=1`** marks the combination the game materialises on spawn. Exactly
  one per multi-combination record.
* `levels 0..0` is a biped-slot window, **not** a level range — power armour
  torsos walk `0..31, 32..35, 36..39 …`.
* each `include` is an `OMOD`, with its record type resolved so typos are obvious.

```sh
fo4tools esp template Data/myplugin.esp --type ARMO --search helmet
```

Sweep a whole plugin with no `--fid`.

## 6. Two plugins override the same record — who wins?

Load order decides, last wins. Check it in `Plugins.txt`:

```sh
grep -n -i 'myplugin' "$WINEPREFIX/drive_c/users/*/AppData/Local/Fallout4/Plugins.txt"
```

```
27:*Tactical Night Vision.esp
28:*fallchildrens_ncr_armor_redux.esp
29:fallchildrens_ncr_armor_redux - TNV.esp
```

**`*` means enabled. No `*` means disabled** — there is no `#` syntax, and a
line that does not start with `*` is simply ignored. (Getting this backwards
cost an hour once.)

Then compare the same record in both files:

```sh
fo4tools esp rec Data/a.esp 010008B1
fo4tools esp rec Data/b.esp 010008B1
```

If the later plugin's copy is missing subrecords the earlier one has, **the
override silently deletes them**. That is exactly how a set of working defaults
disappeared: a one-record patch plugin loaded last and its helmet copy had no
`OBTE`/`OBTS`/`STOP`.

## 7. Verify a plugin is structurally sound

Before shipping, or after any script that rewrites bytes:

```sh
python3 -m fo4tools.test_espwrite Data/myplugin.esp
```

```
myplugin.esp   records=166  sub_ok=166  rec_ok=166  comp_ok=0  bad=0
myplugin.esp   whole-plugin rebuild: BYTE-EXACT (41021 bytes)
RESULT: OK
```

Three levels of proof per record: subrecords parse and re-serialise identically,
the 24-byte header re-renders identically, and the whole plugin rebuilds
byte-for-byte. Against `Fallout4.esm` the same test covers 1,549,276 records
including 56,399 compressed ones.

`fo4tools esp copy` is the manual version of the last step:

```sh
fo4tools esp copy Data/myplugin.esp /tmp/check.esp
# wrote /tmp/check.esp (41021 bytes) — BYTE-EXACT
```

A plugin with nested groups (vanilla masters full of `WRLD`/`CELL`) reports
`DIFFERS` and says why — flattening them is expected, not a bug.

## 8. Bisect a crash or a hang by changing one thing

When the game hangs on load, the question is *which record*. Build single-change
variants and swap them in one at a time:

```sh
# only one default include
fo4tools esp set-template Data/myplugin.esp /tmp/only_visor.esp 020008B1 0200081B

# no template at all
fo4tools esp set-template Data/myplugin.esp /tmp/no_template.esp 020008B1 --drop

# the original configuration
fo4tools esp set-template Data/myplugin.esp /tmp/as_shipped.esp 020008B1 0200081B 020008A1
```

```
wrote /tmp/only_visor.esp (41014 bytes)
  020008B1: defaults -> 0200081B
wrote /tmp/no_template.esp (40967 bytes)
  020008B1: template removed
```

Everything else in the plugin is copied verbatim, so the only variable is the
template. `--drop` is the most informative variant: if the game *still* hangs
with no template, you have been debugging the wrong record.

## 9. Understand a FormID renumbering (and its cost)

Merging another plugin as a **master** shifts every one of your own records:

```
1 master  -> own records 01xxxxxx   (helmet 010008B1)
2 masters -> own records 02xxxxxx   (helmet 020008B1)
```

That is mechanical but it **breaks existing saves** — a save stores the resolved
FormIDs, so an already-owned item no longer resolves. Say so in the changelog; it
is the difference between "update" and "new playthrough".

It also has two traps that no amount of care avoids unless you know them — see
§11.

## 10. Which archive has that mesh?

Record says a NIF, game shows nothing, no error. Find out whether the asset
exists and where:

```sh
fo4tools ba2 list "Data/SomeMod - Main.ba2" | grep -i flashlight
```

```
meshes/Armor/NVRL/FLASHLIGHT/FlashlightAddOnNode_Bright.nif
meshes/Armor/NVRL/FLASHLIGHT/FlashlightMeshFX_Bright.nif
```

To script over every archive:

```sh
for b in Data/*.ba2; do
  n=$(fo4tools ba2 list "$b" 2>/dev/null | grep -c 'FLASHLIGHT/')
  [ "$n" != 0 ] && echo "$n  $b"
done
```

```
14  Data/NVRH Enhanced - Main.ba2
```

Only one archive has them — and that archive is only mounted if the `.ini`
`[Archive]` lists it. A mod can therefore use meshes from a plugin it does not
require: keep the archive, drop the plugin.

Pull one file out to inspect it:

```sh
fo4tools ba2 extract "Data/ReduxRanger - Main.ba2" "ReduxRanger/ReduxHelmet.nif" -o /tmp/x
# extracted meshes/Erynture/ReduxRanger/ReduxHelmet.nif
```

The path argument is a **substring**, and `-o` preserves the archive layout.
`ba2 extract-all` for everything, `ba2 pack` to build an archive.

## 11. The two things that silently produce invisible armour

Both were hit for real while writing this book.

**(a) FormIDs inside `OBTS` are not 4-byte aligned.** An include entry is
`u8 index, u32 formID, u16 pad` (7 bytes), so after a 15-byte header the fids sit
at offsets 16, 23, 30, 37… A renumbering loop that steps `range(0, len, 4)`
rewrites the first include and **corrupts none of the rest** — no error, just
silently wrong mods. Rewrite by scanning every offset and matching exact values.

**(b) `MODL` means two different things.**

| record | `MODL` is |
|---|---|
| `ARMO` | a **list of `ARMA` FormIDs** (the addon link) |
| `ARMA`, `OMOD` | a NIF path string |

Treating `MODL` as text everywhere leaves the armour with no addon link → no
mesh, no error. Check with §4.

The general lesson: after any bulk rewrite, assert. `esp rec` on one `ARMO` and
one `OMOD` catches both of the above in seconds.

## 12. Header forensics

```sh
fo4tools esp header Data/myplugin.esp 0
```

```
sig          TES4
form id      00000000
flags        00000200
size         133
vc           0
form version 0
unknown      0
payload @    24
```

`flags 00000200` = **ESL**. `00000001` = ESM, `00000080` = localised (in which
case `FULL`/`DESC` hold a `u32` string-table index, not a string — `rec` shows
this as a 4-byte payload).

For a record at an arbitrary offset, the same command shows the compressed bit
and where the payload starts; useful when a size field looks wrong:

```
size         583
flags        00040000  (compressed)
form version 131
```

---

## Reference card

| task | command |
|---|---|
| header, masters, counts | `esp info <plugin>` |
| list / search records | `esp dump <plugin> [--type A,B] [--search TXT] [--fid HEX]` |
| every subrecord of one record | `esp rec <plugin> <fid> [--hex] [--max N]` |
| object templates | `esp template <plugin> [--type A] [--search TXT] [--fid HEX]` |
| rewrite / remove defaults | `esp set-template <plugin> <out> <fid> [OMOD…] [--drop]` |
| record header at an offset | `esp header <plugin> <offset>` |
| rebuild a plugin, compare bytes | `esp copy <plugin> <out>` |
| load order health | `order audit [--plugins FILE] [--data DIR]` |
| archive listing / extract / build | `ba2 list\|extract\|extract-all\|pack` |
| writer self-test | `python3 -m fo4tools.test_espwrite <plugin>…` |
| object-template self-test | `python3 -m fo4tools.test_objecttemplate [Fallout4.esm]` |

## When to use xEdit instead

`fo4tools` is deliberately byte-level. Reach for xEdit when you need **typed**
editing: it knows every field of every record, so it names `DATA` bytes as
"Attach Point", "Max Rank", "MaterialSwaps", and it maintains subrecord ordering
and the `XXXX` escape for you. Practically:

* **authoring a new record** from scratch (a recipe, a keyword, an OMOD) — xEdit
* **editing an OMOD's property list** — xEdit, because the property layout varies
  by value type and a 4-byte mistake is silent
* **verifying** what `fo4tools` wrote — xEdit: open the plugin, click the record,
  and confirm the fields read the way you intended
* **inspecting** anything, scripting bulk checks, diffing plugins, or rebuilding
  a plugin byte-exactly — `fo4tools`

They compose well: build and inspect with `fo4tools`, sanity-check the result in
xEdit.

## Writing your own checks

The library is small and stdlib-only, so ad-hoc queries are a few lines.

```python
# run from the fo4tools repo root (or put it on sys.path)
from fo4tools import espread, espwrite, objecttemplate

buf, recs = espread.load("Data/myplugin.esp")

# find a record by editor id
rec = next(r for r in recs if r.type == "ARMO" and r.edid == "0ArmorReduxHelmet")

# named subrecord access
subs = dict(espread.subrecords(rec.data))
print(subs["MODL"].hex())          # -> the ARMA form id, see §4

# decode its defaults
obte, templates, _ = objecttemplate.parse_record(rec, espread.subrecords(rec.data))
for t in templates:
    print("default" if t.default else "alt", [hex(i.mod) for i in t.includes])

# re-serialise losslessly, and rebuild a record byte-for-byte
assert espwrite.serialize_subrecords(espread.subrecords(rec.data)) == rec.data
```

```
MODL: 00080002
default ['0x200081b', '0x20008a1']
```

For a whole-plugin reference check after a rewrite — a smoke test that catches
most of the damage from §11:

```python
import struct
from fo4tools import espread

buf, recs = espread.load("Data/myplugin.esp")
self_fids = {r.fid for r in recs if (r.fid >> 24) == 2}

bad = []
for r in recs[1:]:                              # skip TES4: HEDR's "next id"
    for sig, p in espread.subrecords(r.data):   # has the same high byte
        if sig in ("EDID", "FULL", "DESC") or len(p) % 4:
            continue
        for i in range(0, len(p), 4):
            v = struct.unpack_from("<I", p, i)[0]
            if (v >> 24) == 2 and v not in self_fids:
                bad.append((hex(r.fid), sig, hex(v)))

print(bad or "ok — every aligned self-reference resolves")
```

```
ok — every aligned self-reference resolves
```

Two caveats, both learned by getting them wrong:

* Skipping `recs[0]` matters. The TES4 header's `HEDR.next id` (`0x02000940`)
  shares the high byte with your own records and is not one.
* This aligned loop **cannot see `OBTS` includes** (§11a), so a clean result is
  necessary but not sufficient. It is a smoke test; a renumberer must scan every
  offset and then re-check what it wrote.
