import unittest

from _loader import load_pure_module


class FakeMessage:
    def __init__(self, type_: str, data=None):
        self.type = type_
        self.data = data


class RemovePrivateMentionsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.md = load_pure_module('message_delivery')

    def test_strips_at_segment_and_its_trailing_newline(self) -> None:
        message = [FakeMessage('at', '10001'), '\n', '你今天的黑丝来啦！', FakeMessage('image', b'x')]
        result = self.md.remove_private_mentions(message, FakeMessage)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], '你今天的黑丝来啦！')
        self.assertEqual(result[1].type, 'image')

    def test_keeps_a_newline_that_does_not_follow_an_at(self) -> None:
        message = ['一行', '\n', '两行']
        self.assertEqual(self.md.remove_private_mentions(message, FakeMessage), message)

    def test_plain_string_passes_through(self) -> None:
        self.assertEqual(self.md.remove_private_mentions('文字', FakeMessage), '文字')

    def test_message_that_is_only_an_at_becomes_empty_string(self) -> None:
        self.assertEqual(self.md.remove_private_mentions(FakeMessage('at', '1'), FakeMessage), '')


if __name__ == '__main__':
    unittest.main()
