"""GNRL layout tests using an independently constructed compressed record."""
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from fo4tools import ba2


class GeneralArchiveTests(unittest.TestCase):
    def test_writer_layout_and_uncompressed_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / 'test.ba2'
            payload = b'PEX payload\0' * 100
            ba2.write_ba2(archive, [('Scripts/test.pex', payload)])
            raw = archive.read_bytes()
            magic, version, kind, count, names = struct.unpack_from('<4sI4sIQ', raw)
            self.assertEqual((magic, version, kind, count), (b'BTDX', 1, b'GNRL', 1))
            _, _, _, _, offset, packed, unpacked, sentinel = struct.unpack_from('<I4sIIQIII', raw, 24)
            self.assertEqual((offset, packed, unpacked, sentinel), (60, 0, len(payload), 0xBAADF00D))
            self.assertEqual(names, 60 + len(payload))
            self.assertEqual(raw[offset:offset + unpacked], payload)
            self.assertEqual(ba2.list_names(archive), ['Scripts/test.pex'])
            out = Path(tmp) / 'out'
            self.assertEqual(ba2.extract_all(archive, out), 1)
            self.assertEqual((out / 'Scripts/test.pex').read_bytes(), payload)

    def test_compressed_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / 'test.ba2'
            payload = b'compressed fixture' * 1000
            compressed = zlib.compress(payload)
            name = b'Scripts\\compressed.pex'
            header = struct.pack('<4sI4sIQ', b'BTDX', 1, b'GNRL', 1, 60 + len(compressed))
            record = struct.pack('<I4sIIQIII', 0, b'pex\0', 0, 0x100100, 60,
                                 len(compressed), len(payload), 0xBAADF00D)
            archive.write_bytes(header + record + compressed + struct.pack('<H', len(name)) + name)
            out = Path(tmp) / 'out'
            ba2.extract_file(archive, 'compressed.pex', out)
            self.assertEqual((out / 'Scripts/compressed.pex').read_bytes(), payload)

    def test_empty_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / 'empty.ba2'
            ba2.write_ba2(archive, [])
            self.assertEqual(ba2.list_names(archive), [])


if __name__ == '__main__':
    unittest.main()
