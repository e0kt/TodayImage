import base64
import tempfile
import unittest
from pathlib import Path

from _loader import load_pure_module

PNG = b'\x89PNG\r\n\x1a\n' + b'x' * 32
JPG = b'\xff\xd8\xff' + b'x' * 32
GIF = b'GIF89a' + b'x' * 32
BMP = b'BM' + b'x' * 32
WEBP = b'RIFF' + b'0000' + b'WEBP' + b'x' * 32


class Segment:
    def __init__(self, type_, data):
        self.type = type_
        self.data = data


class FakeEvent:
    def __init__(self, content=None, image_list=None, image=None):
        self.content = content
        self.image_list = image_list
        self.image = image


class CollectRefsTests(unittest.TestCase):
    def setUp(self):
        self.mod = load_pure_module('image_input')

    def test_collects_from_content_segments(self):
        ev = FakeEvent(content=[Segment('image', 'a.png'), Segment('text', 'ignored')])
        self.assertEqual(self.mod.collect_image_refs(ev), ('a.png',))

    def test_collects_from_all_three_fields_and_deduplicates(self):
        # Adapters differ in where they hang an attachment; all three must be checked.
        ev = FakeEvent(
            content=[Segment('img', 'a.png')],
            image_list=['b.png', 'a.png'],
            image='c.png',
        )
        self.assertEqual(self.mod.collect_image_refs(ev), ('a.png', 'b.png', 'c.png'))

    def test_empty_event_yields_nothing(self):
        self.assertEqual(self.mod.collect_image_refs(FakeEvent()), ())


class SuffixTests(unittest.TestCase):
    def setUp(self):
        self.mod = load_pure_module('image_input')

    def test_magic_bytes_win_over_a_lying_extension(self):
        self.assertEqual(self.mod.detect_image_suffix(PNG, 'photo.jpg'), '.png')

    def test_every_supported_format_is_sniffed(self):
        for data, expected in ((PNG, '.png'), (JPG, '.jpg'), (GIF, '.gif'), (BMP, '.bmp'), (WEBP, '.webp')):
            with self.subTest(expected=expected):
                self.assertEqual(self.mod.detect_image_suffix(data, 'x'), expected)

    def test_falls_back_to_the_source_extension(self):
        self.assertEqual(self.mod.detect_image_suffix(b'unknown-bytes', 'photo.webp'), '.webp')

    def test_url_query_string_is_stripped(self):
        self.assertEqual(self.mod.image_suffix_from_source('https://h/x.png?a=1'), '.png')

    def test_unknown_extension_yields_empty(self):
        self.assertEqual(self.mod.image_suffix_from_source('https://h/x.txt'), '')


class ReadImageBytesTests(unittest.TestCase):
    def setUp(self):
        self.mod = load_pure_module('image_input')

    def test_reads_a_local_file(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'a.png'
            path.write_bytes(PNG)
            data, suffix = self.mod.read_image_bytes(str(path), 1024)
            self.assertEqual(data, PNG)
            self.assertEqual(suffix, '.png')

    def test_reads_a_data_uri(self):
        source = 'data:image/png;base64,' + base64.b64encode(PNG).decode()
        data, suffix = self.mod.read_image_bytes(source, 1024)
        self.assertEqual(data, PNG)
        self.assertEqual(suffix, '.png')

    def test_reads_a_base64_scheme(self):
        source = 'base64://' + base64.b64encode(JPG).decode()
        data, suffix = self.mod.read_image_bytes(source, 1024)
        self.assertEqual(data, JPG)
        self.assertEqual(suffix, '.jpg')

    def test_rejects_oversize_content(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'a.png'
            path.write_bytes(PNG + b'y' * 4096)
            self.assertIsNone(self.mod.read_image_bytes(str(path), 64))

    def test_rejects_non_image_content(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'a.txt'
            path.write_bytes(b'just some text')
            self.assertIsNone(self.mod.read_image_bytes(str(path), 1024))

    def test_rejects_missing_file_and_empty_source(self):
        self.assertIsNone(self.mod.read_image_bytes('/definitely/not/here.png', 1024))
        self.assertIsNone(self.mod.read_image_bytes('', 1024))

    def test_link_scheme_prefix_is_stripped(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'a.png'
            path.write_bytes(PNG)
            data, _ = self.mod.read_image_bytes(f'link://{path}', 1024)
            self.assertEqual(data, PNG)


if __name__ == '__main__':
    unittest.main()
