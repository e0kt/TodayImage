import unittest

from _loader import load_pure_module


class UploadAccessTests(unittest.TestCase):
    def setUp(self):
        self.mod = load_pure_module('upload_access')

    def test_master_is_authorised_without_a_whitelist_entry(self):
        self.assertTrue(self.mod.can_upload_images('10001', ['10001'], []))

    def test_whitelisted_user_is_authorised(self):
        self.assertTrue(self.mod.can_upload_images('10002', [], ['10002']))

    def test_everyone_else_is_refused(self):
        self.assertFalse(self.mod.can_upload_images('10003', ['10001'], ['10002']))

    def test_whitelist_parses_from_a_delimited_string(self):
        self.assertTrue(self.mod.can_upload_images('10002', [], '10001, 10002 10003'))

    def test_ids_are_compared_as_trimmed_strings(self):
        self.assertTrue(self.mod.can_upload_images(10002, [], [' 10002 ']))

    def test_empty_user_id_is_refused(self):
        self.assertFalse(self.mod.can_upload_images('', [], ['']))

    def test_garbage_whitelist_shapes_degrade_to_empty(self):
        self.assertEqual(self.mod.normalized_user_ids(None), frozenset())
        self.assertEqual(self.mod.normalized_user_ids(42), frozenset())


if __name__ == '__main__':
    unittest.main()
