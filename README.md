# fo4tools

A command-line toolkit for Fallout 4 asset formats — pure Python standard
library (`struct` + `zlib` + `xml`), no game, no Blender, no external tools.

* **hkx** — reads Fallout 4 animations from binary `.hkx` (natively, no
  hkxcmd) or hkxpack TagXML, decompresses them to per-bone per-frame values,
  and writes binary `.hkx`.
* **clip** — clip-level operations: pose diffing, rebasing, camera transfer,
  delta application.
* **graph** — hkb behaviour-graph (TagXML) inspection and repair.
* **ba2** — Bethesda archives, GNRL and DX10, read and write.
* **esp** — plugin inspection (read-only).
* **order** — load-order audit.
* **animtext / clipinfo / nif** — auxiliary format readers.

---

## Quick start

No installation. Run the launcher directly, or symlink it into your `PATH`:

```sh
bin/fo4tools --help
ln -s "$PWD/bin/fo4tools" ~/.local/bin/fo4tools
```

Everything path-related is a command-line argument; the repo works from any
checkout location.

---

## Commands

### hkx — animation data

**`fo4tools hkx info <file>`**

Print a summary of one animation: duration, frame count and rate, track count,
block layout, skeleton (if the file carries one), annotations, and which bones
are actually animated.

```sh
fo4tools hkx info meshes/actors/character/_1stperson/animations/357cm/2hand/wpnidleemptyready.hkx
```

**`fo4tools hkx dump <file> [--bone NAME] [--motion]`**

Dump per-frame rotations (and translations, where present) for every track.

* `--bone NAME` — only this bone (case-insensitive match on the bone name).
* `--motion` — only tracks that actually move (more than one frame of data).

```sh
fo4tools hkx dump clip.hkx --bone Weapon
fo4tools hkx dump clip.hkx --motion
```

**`fo4tools hkx meta <path> [--compare DIR] [--only-diffs]`**

Summarize the scalar metadata of one unpacked TagXML (type, frames, tracks,
duration, bone-map fingerprint, annotations), or of a whole directory. With
`--compare DIR`, diff two directories keyed by filename.

* `--only-diffs` — in compare mode, skip keys that are identical.

**`fo4tools hkx bind-fix <file.xml> [...] [--check]`**

Rewrite an empty `transformTrackToBoneIndices` into the full identity map
(0..N−1), matching what vanilla Fallout 4 anims ship. Only touches the binding
array; the spline payload is untouched.

* `--check` — report what would be patched without writing.

### clip — clip operations

All clip commands read the same formats as `hkx` and write binary `.hkx`.
Bone names and parents come from the animation's own skeleton when the file
carries one; otherwise the built-in FO4 95-bone rig is used.

**`fo4tools clip delta <mod> <vanilla> [--threshold DEG]`**

Compare the frame-0 pose of two clips, bone by bone, and report which bones
differ by more than a threshold. Useful to check whether two files are "the
same animation, re-posed".

* `--threshold DEG` — minimum rotation difference to report (default 2.0°).

```sh
fo4tools clip delta myclip.hkx vanilla.hkx --threshold 1.5
```

**`fo4tools clip rebase <clip> <ref> <out>`**

Rebase a clip so that its frame 0 equals the reference pose while preserving
all motion. Processed parent-first, so every bone sees its parent's already
corrected transform.

**`fo4tools clip copy-cameras <mod> <vanilla> <out>`**

Give a mod clip the camera bone positions (`Camera`, `CamTarget`,
`AnimObjectA`, `AnimObjectB`) of its vanilla counterpart, keeping everything
else in the mod clip (stance, rotations, motion). Skips the write (with a
message) when no camera data is present.

**`fo4tools clip apply-delta <vanilla> <mod> <out> [--root LIST]`**

Rebuild a clip as *vanilla + the mod's pose delta*: keeps vanilla's complete
track set, frame count and timing, and rotates every non-root bone by the
delta between the two frame-0 poses.

* `--root LIST` — comma-separated root-chain bones that keep the mod's values
  directly instead of the delta (default `COM,Pelvis,Spine1`). Use this when
  the two files store body orientation on different bones.

### graph — behaviour graphs

**`fo4tools graph index <xml>`**

List every hkb object (`#id`, class, name) with its reverse references — who
points at whom. The basis for graph surgery.

**`fo4tools graph vars <xml>`**

Print the `hkbBehaviorGraphStringData` variable names, one per line.

**`fo4tools graph events <xml>`**

Print the event names, one per line.

### ba2 — Bethesda archives

Handles both archive kinds: GNRL (meshes, materials, misc) and DX10 (texture
archives). Writers produce archives whose hashes match Bethesda's tools
byte-for-byte.

**`fo4tools ba2 list <archive> [substring]`**

List archive contents; an optional substring filters the listing.

```sh
fo4tools ba2 list "fallchildrens_ncr_armor_redux - Main.ba2" ReduxHelmet
```

**`fo4tools ba2 extract <archive> <path> -o DIR`**

Extract one file (matched by a substring of its archive path) into `DIR`,
preserving the path.

```sh
fo4tools ba2 extract data.ba2 ReduxHelmet.nif -o /tmp/out
```

**`fo4tools ba2 extract-all <archive> [-o DIR] [substring]`**

Extract every file (optionally filtered by substring) into `DIR`
(default `.`). DX10 archives extract as full-mip-chain `.dds` files.

**`fo4tools ba2 pack <out.ba2> <dir> [--dx10]`**

Pack a directory tree into an archive. Without `--dx10`, a GNRL archive of any
file types. With `--dx10`, a DX10 texture archive: the directory's `.dds`
files are split into mip chunks and zlib-compressed, Bethesda-style.

```sh
fo4tools ba2 pack "mod - Main.ba2"   Data/meshes
fo4tools ba2 pack "mod - Textures.ba2" Data/textures --dx10
```

### esp — plugins

**`fo4tools esp info <plugin>`**

Header information: version, record count, next object id, author, masters,
and a per-type record tally.

**`fo4tools esp dump <plugin> [--type LIST] [--search TEXT] [--fid HEX]`**

List records as `formID TYPE EDID FULL-name`:

* `--type LIST` — comma-separated record types, e.g. `ARMO,OMOD`
* `--search TEXT` — substring of EDID or FULL name (case-insensitive)
* `--fid HEX` — exact form id, e.g. `01000F99`

```sh
fo4tools esp dump mod.esp --type OMOD --search Flashlight
```

**`fo4tools esp template <plugin> [--type LIST] [--search TEXT] [--fid HEX]`**

Decode the object template (`OBTE`/`OBTF`/`OBTS`/`STOP`) on each record: one
line per template combination showing the level/slot range, the `default`
marker, keywords, and each include's `OMOD` (with its resolved record type).

```sh
fo4tools esp template fallout4.esm --fid 0024A401     # a power-armour torso
fo4tools esp template mod.esp --type ARMO --search helmet
```

**`fo4tools esp rec <plugin> <fid> [--hex] [--max N]`**

Dump every subrecord of one record: sig, length, payload (hex, with an ASCII
tail when printable), and — for short payloads — the leading FormIDs resolved to
record types. This is the workhorse for “what is actually in this record?”.

```sh
fo4tools esp rec mod.esp 010008A1
```

**`fo4tools esp set-template <plugin> <out> <fid> [OMOD...] [--drop]`**

Rewrite (or remove with `--drop`) a record's default object template. The
includes are OMOD form ids for the single `default=1` combination; the
`OBTE`/`OBTS`/`STOP` triple is emitted after `APPR`. Everything else is copied
verbatim, so this is the intended way to change “what spawns by default”
without hand-editing bytes.

```sh
# as shipped by Redux: visor + helmet material, no flashlight
fo4tools esp set-template mod.esp out.esp 010008B1 0100081B 010008CF
# bisect a suspected default:
fo4tools esp set-template mod.esp only_visor.esp 010008B1 0100081B
```

**`fo4tools esp header <plugin> <offset>`**

Decode the 24-byte record header at a file offset: signature, form id, flags
(incl. the `compressed` bit), payload size, version control info, form version,
and where the payload starts.

**`fo4tools esp copy <plugin> <out> [--nested]`**

Rebuild a plugin through the writer and compare to the source. For plugins with
single-level top groups (anything produced by `espwrite` / the `build_*`
scripts) this reproduces the file **byte-for-byte**, which doubles as a writer
self-check. Deeply nested vanilla masters (WRLD/CELL) are flattened, so the
result differs; the command says so rather than pretending otherwise.

```sh
fo4tools esp copy mod.esp /tmp/check.esp      # -> "BYTE-EXACT"
```

### Writing plugins (library)

`fo4tools.espwrite` is the write-side counterpart to `espread` and is pure
stdlib:

* `parse_subrecords` / `serialize_subrecords` — subrecord streams, including
  the `XXXX` escape for payloads over 64 KiB.
* `render_record` — a full 24-byte-header record, uncompressed or zlib-
  compressed (`vc` / `form_version` / `unknown` are explicit fields).
* `render_group` / `render_tes4` — GRUP and TES4 header authoring (masters,
  ESL/ESM/localised flags, `HEDR`).
* `Record`, `Group`, `Plugin` — small mutable objects (`set`/`remove`/`get` on
  subrecords, `to_bytes()`, `write()`).

Fidelity is tested, not assumed: `python3 -m fo4tools.test_espwrite FILE`
checks every record's subrecord round-trip and header re-render. Against
`Fallout4.esm` that is **1,549,276 records, 0 failures** (1,492,877
uncompressed records re-render byte-identically, 56,399 compressed ones
decompress to identical payloads). `python3 -m fo4tools.test_objecttemplate`
likewise round-trips all 2,430 `OBTS` records.

### order — load order

**`fo4tools order audit [--plugins FILE] [--data DIR]`**

Audit a `Plugins.txt` against a Data directory (read-only) and report:

* entries with no matching file in Data,
* enabled plugins whose masters are missing,
* ordering violations (a master loading after its dependent),
* full-plugin and ESL capacity,
* a per-plugin header table (ESL/ESM/ESP, version, master count).

Defaults: `--plugins Plugins.txt --data Data`.

```sh
fo4tools order audit --plugins ~/AppData/Local/Fallout4/Plugins.txt --data ~/games/fo4/Data
```

### animtext — AnimTextData

**`fo4tools animtext <file>`**

Decode and print either file format: `AnimationOffsets` (the `V4` binary with
the behaviour path and per-animation entry table) or `AnimationFileData` (the
text manifest of behaviour and clip paths).

### clipinfo — behaviour clip info

**`fo4tools clipinfo <file>`**

Decode the two-section behaviour/clip information file and print the block and
section headers with their record counts.

### nif — NiStream

**`fo4tools nif <file>`**

Dump a FO4 NiStream as JSON: geometry (vertices, UVs, normals, triangles),
the NiNode hierarchy with transforms, and texture paths. Aimed at the weapon
`44.nif` family; other block types may not parse.

---

## Notes

* **hkx write support** — all four `clip` operations write binary HKX; the
  outputs re-load cleanly.
* **ba2 verification** — the GNRL writer's hash scheme was verified against
  the vanilla `fallout4 - animations.ba2` (2000/2000 matches); the DX10
  writer round-trips every texture byte-for-byte against a working archive.
* **esp is read-only for the CLI** — `esp info/dump/template/header` inspect;
  `esp copy` writes a rebuilt plugin. Full record authoring is available as a
  library (`fo4tools.espwrite`), not as a CLI editing language.

## Layout

```
bin/fo4tools          launcher
fo4tools/
  cli.py              argparse dispatcher
  hkx.py              animation reader/writer (binary + TagXML)
  clip.py             clip operations
  hkxmeta.py          TagXML metadata summaries
  graph.py            behaviour graphs + binding repair
  ba2.py              GNRL archives
  dx10.py             DX10 texture archives (DDS <-> chunks)
  espread.py          plugin record walker
  espwrite.py         plugin writer (subrecords, records, groups, TES4)
  objecttemplate.py   OBTE/OBTS object-template decoder + builder
  test_espwrite.py    writer self-test (round-trip vs any plugin)
  test_objecttemplate.py  OBTS round-trip self-test
  loadorder.py        load-order auditor
  animtext.py         AnimTextData formats
  clipinfo.py         behaviour clip info format
  nif.py              NiStream parser
```
