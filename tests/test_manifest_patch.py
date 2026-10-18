"""Security checks for the narrow binary XML mutation (no external packages)."""
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from patch_manifest import INTERNET, patch, pool_strings


def fixture(utf8, permission_tag="uses-permission", permission=INTERNET):
    strings = ["manifest", permission_tag, "name", "http://schemas.android.com/apk/res/android", permission, "application"]
    encoded, offsets = bytearray(), []
    for value in strings:
        offsets.append(len(encoded))
        if utf8:
            raw = value.encode()
            encoded.extend(bytes([len(value), len(raw)]) + raw + b"\0")
        else:
            encoded.extend(struct.pack("<H", len(value)) + value.encode("utf-16le") + b"\0\0")
    encoded.extend(b"\0" * (-len(encoded) % 4))
    start = 28 + 4 * len(strings)
    pool = struct.pack("<HHIIIIII", 1, 28, start + len(encoded), len(strings), 0, 0x100 if utf8 else 0, start, 0)
    pool += struct.pack("<" + "I" * len(offsets), *offsets) + encoded

    def node(name, attributes=b""):
        count = len(attributes) // 20
        return struct.pack("<HHIII", 0x102, 16, 36 + len(attributes), 1, 0xffffffff) + struct.pack("<IIHHHHHH", 0xffffffff, name, 20, 20, count, 0, 0, 0) + attributes

    def end(name):
        return struct.pack("<HHIIIII", 0x103, 16, 24, 1, 0xffffffff, 0xffffffff, name)

    attr = struct.pack("<IIIHBBI", 3, 2, 4, 8, 0, 3, 4)
    chunks = [pool, node(0), node(1, attr), end(1), node(5), end(5), end(0)]
    content = b"".join(chunks)
    return struct.pack("<HHI", 3, 8, 8 + len(content)) + content, chunks


class ManifestPatchTests(unittest.TestCase):
    def test_removes_only_permission_element_with_both_string_encodings(self):
        for utf8 in (True, False):
            for tag in ("uses-permission", "uses-permission-sdk-23"):
                with self.subTest(utf8=utf8, tag=tag):
                    source, chunks = fixture(utf8, tag)
                    result, count = patch(source)
                    expected_content = b"".join(chunks[:2] + chunks[4:])
                    self.assertEqual(result, struct.pack("<HHI", 3, 8, 8 + len(expected_content)) + expected_content)
                    self.assertEqual(count, 1)
                    # INTERNET remains in the string pool; searching raw bytes
                    # is not a valid permission check.
                    self.assertIn(INTERNET, pool_strings(chunks[0]))

    def test_rejects_other_permissions_and_internet_on_nonpermission_tags(self):
        for tag, value in [("uses-permission", "android.permission.RECORD_AUDIO"), ("application", INTERNET)]:
            with self.subTest(tag=tag, value=value), self.assertRaises(ValueError):
                patch(fixture(True, tag, value)[0])

    def test_rejects_truncated_document(self):
        with self.assertRaises(ValueError):
            patch(fixture(True)[0][:-1])


if __name__ == "__main__":
    unittest.main()
