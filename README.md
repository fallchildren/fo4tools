# fo4tools

Command-line toolkit for Fallout 4 asset formats. Pure Python standard library
(struct + zlib + xml), no game, no Blender, no external tools.

```
fo4tools hkx info <file>                 animation summary (binary .hkx or TagXML)
fo4tools hkx dump <file> [--bone X]      per-bone per-frame values
fo4tools hkx meta <file|dir> [--compare DIR]   TagXML scalar metadata / dir diff
fo4tools hkx bind-fix <file.xml> [...]   identity-map transformTrackToBoneIndices

fo4tools clip delta <a> <b>              pose diff between two clips
fo4tools clip rebase <clip> <ref> <out>  rebase a clip onto a reference pose
fo4tools clip copy-cameras <mod> <vanilla> <out>   vanilla camera bone positions
fo4tools clip apply-delta <vanilla> <mod> <out>    rebuild as vanilla + pose delta

fo4tools graph index <xml>               hkb behaviour-graph object index
fo4tools graph vars <xml>                variable names
fo4tools graph events <xml>              event names

fo4tools ba2 list <archive>              contents (GNRL + DX10)
fo4tools ba2 extract <archive> <path> -o DIR
fo4tools ba2 extract-all <archive> -o DIR
fo4tools ba2 pack <out.ba2> <dir> [--dx10]

fo4tools esp info <plugin>               header, masters, record counts
fo4tools esp dump <plugin> [--type ..] [--search ..] [--fid ..]

fo4tools order audit [--plugins ..] [--data ..]

fo4tools animtext <file>                 AnimationOffsets / AnimationFileData
fo4tools clipinfo <file>                 behaviour clip information
fo4tools nif <file>                      NiStream dump (BSTriShape weapons)
```

## Notes

- **hkx**: reads binary HKX natively (spline + lossless + interleaved
  decompression) and hkxpack TagXML. Writes binary HKX — all four clip
  operations write files that re-load cleanly.
- **clip**: bone names/parents come from the animation's own skeleton when the
  file carries one; otherwise the built-in FO4 95-bone rig is used as fallback.
- **ba2**: GNRL and DX10 archives; the writers produce archives whose hashes
  match Bethesda's tools byte-for-byte (verified against vanilla
  `fallout4 - animations.ba2` and a working DX10 archive).
- **nif**: minimal parser, aimed at the weapon `44.nif` family; other block
  types may not parse.
- **esp**: read-only record walker (no compressed-record writing).

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
  loadorder.py        load-order auditor
  animtext.py         AnimTextData formats
  clipinfo.py         behaviour clip info format
  nif.py              NiStream parser
```

Based on tooling originally developed for a FO4 animation-authoring pipeline;
the spline decompression traces to HavokLib (GPL-3.0).
