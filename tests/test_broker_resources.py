import unittest
from test_manifest_patch import fixture
from patch_manifest import pool_strings, u32
from remap_resources import remap_value, remap_resources

ALIASES = {"com.google.android.gms": "com.offline.denied.gms"}


class BrokerResourceTests(unittest.TestCase):
    def test_exact_packages_components_and_authorities_without_sdk_class_names(self):
        for value in ("com.google.android.gms", "com.google.android.gms/.Service", "content://com.google.android.gms.chimera/api", "com.google.android.gms.phenotype"):
            self.assertNotEqual(remap_value(value, ALIASES), value)
        for value in ("com.google.android.gms.common.GoogleApiAvailability", "Lcom/google/android/gms/common/GoogleApiAvailability;", "com.google.android.gmsfake"):
            self.assertEqual(remap_value(value, ALIASES), value)

    def test_resource_pools_preserve_indices_and_lengths_in_both_encodings(self):
        for utf8 in (True, False):
            source = fixture(utf8, permission="com.google.android.gms")[0]
            result, count = remap_resources(source, ALIASES)
            self.assertEqual(count, 1)
            self.assertEqual(len(result), len(source))
            self.assertEqual(u32(result, 4), len(result))
            size = u32(result, 12)
            before = pool_strings(source[8:8 + size])
            after = pool_strings(result[8:8 + size])
            self.assertEqual(after, [ALIASES.get(value, value) for value in before])

    def test_android_surrogate_encoded_strings_survive_broker_remapping(self):
        for utf8 in (True, False):
            source = fixture(utf8, permission="com.google.android.gms", extra_strings=["\ud83d\ude00"])[0]
            result, count = remap_resources(source, ALIASES)
            self.assertEqual(count, 1)
            size = u32(result, 12)
            self.assertEqual(pool_strings(result[8:8 + size])[-1], "\ud83d\ude00" if utf8 else "\U0001f600")
