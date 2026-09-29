"""把「被回复的那张图」匹配回图库里的文件。

这是识别的正路：适配器其实会把被回复的图放进 ev.image / ev.image_list
（早期调研只采样了回复文字消息的事件，误判为拿不到）。
拿到图本身就不必依赖发送回执，也不怕核心重启清空内存表。
"""
import hashlib
import tempfile
import unittest
from pathlib import Path

from _loader import load_pure_module

PNG = b'\x89PNG\r\n\x1a\n' + b'A' * 256
JPG = b'\xff\xd8\xff' + b'B' * 256


class ExactMatchTests(unittest.TestCase):
    def setUp(self):
        self.im = load_pure_module('image_match')
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.files = {}
        for name, blob in (('a.png', PNG), ('b.jpg', JPG), ('c.png', PNG + b'X')):
            p = self.root / name
            p.write_bytes(blob)
            self.files[name] = str(p)

    def tearDown(self):
        self.temp.cleanup()

    def test_finds_the_byte_identical_file(self):
        hit = self.im.find_exact(PNG, self.files.values())
        self.assertEqual(hit, self.files['a.png'])

    def test_returns_none_when_nothing_matches(self):
        self.assertIsNone(self.im.find_exact(b'not in the gallery', self.files.values()))

    def test_size_filter_avoids_hashing_everything(self):
        # 先按体积筛，只对体积相同的少数文件算哈希 —— 图库有几万张，
        # 无差别哈希会让一条低频的管理命令变得很慢。
        hashed = []
        orig = self.im._sha256_file

        def counting(path):
            hashed.append(path)
            return orig(path)

        self.im._sha256_file = counting
        try:
            self.im.find_exact(PNG, self.files.values())
        finally:
            self.im._sha256_file = orig
        # b.jpg 体积不同，不该被哈希
        self.assertNotIn(self.files['b.jpg'], hashed)

    def test_same_size_different_content_is_not_a_match(self):
        # c.png 比 a.png 多一字节，体积不同；构造一个等长但不同内容的
        other = self.root / 'd.png'
        other.write_bytes(b'\x89PNG\r\n\x1a\n' + b'Z' * 256)
        hit = self.im.find_exact(PNG, [str(other)])
        self.assertIsNone(hit)

    def test_unreadable_file_is_skipped_not_raised(self):
        hit = self.im.find_exact(PNG, [str(self.root / 'missing.png'), self.files['a.png']])
        self.assertEqual(hit, self.files['a.png'])

    def test_empty_inputs(self):
        self.assertIsNone(self.im.find_exact(b'', self.files.values()))
        self.assertIsNone(self.im.find_exact(PNG, []))


class PerceptualMatchTests(unittest.TestCase):
    """QQ 若重新编码，字节比对会失效，此时退到感知哈希。

    仅用于**很小的候选集**（当天该会话该类型的记录），
    对整个图库解码几万张图是不可接受的。
    """

    def setUp(self):
        self.im = load_pure_module('image_match')

    def test_reports_unavailable_without_pillow(self):
        # 纯模块不硬依赖 Pillow；不可用时返回 None 而不是抛异常
        result = self.im.find_similar(b'not-an-image', ['/nope.png'], max_distance=8)
        self.assertIsNone(result)

    def test_empty_candidates_returns_none(self):
        self.assertIsNone(self.im.find_similar(PNG, [], max_distance=8))


if __name__ == '__main__':
    unittest.main()


class SimilarCandidateCapTests(unittest.TestCase):
    """感知哈希要解码图片，实测 200 张 5 秒多 —— 候选集必须很小。"""

    def setUp(self):
        self.im = load_pure_module('image_match')

    def test_too_many_candidates_is_abandoned_not_slowly_computed(self):
        many = [f'/img/{i}.png' for i in range(self.im.MAX_SIMILAR_CANDIDATES + 1)]
        self.assertIsNone(self.im.find_similar(PNG, many, max_distance=8))

    def test_cap_is_small_enough_to_stay_fast(self):
        self.assertLessEqual(self.im.MAX_SIMILAR_CANDIDATES, 64)
