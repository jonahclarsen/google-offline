import hashlib
import struct
import unittest
import zlib
from unittest.mock import patch as mock_patch
from test_manifest_patch import fixture
from clone_apk import CLONE_PACKAGE, ORIGINAL_PACKAGE, dex_strings, label_manifest, rewrite_dex, trust_clone_signer, CERT_PAYLOAD, DEVELOPMENT_CERT, backup_disabled
from patch_manifest import pool_strings, u32


def sample_dex():
    strings = [b"com.google.android.inputmethod.korean", ORIGINAL_PACKAGE.encode(), ORIGINAL_PACKAGE.encode() + b".provider", b"com.google.android.inputmethod.pinyin"]
    header = bytearray(112)
    header[:8] = b"dex\n035\0"
    struct.pack_into("<II", header, 56, len(strings), 112)
    offsets, data = [], bytearray()
    for value in strings:
        offsets.append(112 + 4 * len(strings) + len(data))
        data.extend(bytes([len(value)]) + value + b"\0")
    return bytes(header) + struct.pack("<IIII", *offsets) + data


class CloneTests(unittest.TestCase):
    def test_dex_package_rebinding_preserves_order_and_updates_checksums(self):
        data = rewrite_dex(sample_dex())
        strings = dex_strings(data)
        self.assertEqual(strings, sorted(strings))
        self.assertEqual(strings[1], CLONE_PACKAGE.encode())
        self.assertEqual(data[12:32], hashlib.sha1(data[32:]).digest())
        self.assertEqual(u32(data, 8), zlib.adler32(data[12:]) & 0xffffffff)

    def test_unsafe_namespace_that_breaks_dex_order_is_rejected(self):
        with mock_patch("clone_apk.CLONE_PACKAGE", "com.aaaaaa.android.inputmethod.latin"):
            with self.assertRaises(ValueError):
                rewrite_dex(sample_dex())

    def test_trust_update_is_an_exact_certificate_payload_replacement(self):
        digest = hashlib.sha256(b"our signing certificate").digest()
        source = b"prefix" + CERT_PAYLOAD + b"suffix"
        result, count = trust_clone_signer(source, digest)
        self.assertEqual(count, 1)
        self.assertEqual(result, b"prefix" + CERT_PAYLOAD[:8] + digest + b"suffix")
        for bad in (DEVELOPMENT_CERT, CERT_PAYLOAD * 2):
            with self.assertRaises(ValueError):
                trust_clone_signer(bad, digest)
        self.assertEqual(trust_clone_signer(b"unrelated", digest), (b"unrelated", 0))

    def test_inline_app_label_with_both_manifest_string_encodings(self):
        for utf8 in (True, False):
            with self.subTest(utf8=utf8):
                source, chunks = fixture(utf8, include_label=True)
                result = label_manifest(source)
                self.assertEqual(len(result), u32(result, 4))
                pool_size = u32(result, 12)
                strings = pool_strings(result[8:8 + pool_size])
                self.assertEqual(strings[:-1], pool_strings(chunks[0]))
                self.assertEqual(strings[-1], "Gboard Offline")
                offset = 8 + pool_size + sum(len(c) for c in chunks[1:4])
                application = result[offset:]
                self.assertEqual(u32(application, 44), len(strings) - 1)
                self.assertEqual(application[51], 3)
                self.assertEqual(u32(application, 52), len(strings) - 1)

    def test_clone_disables_cloud_backup_with_both_string_encodings(self):
        for utf8 in (True, False):
            source = fixture(utf8, include_label=True, include_backup=True)[0]
            self.assertFalse(backup_disabled(source))
            self.assertTrue(backup_disabled(label_manifest(source)))


if __name__ == "__main__":
    unittest.main()
