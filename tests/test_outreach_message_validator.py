import unittest
from unittest.mock import patch

class TestMessageValidator(unittest.TestCase):
    def setUp(self):
        self.patcher = patch('app.outreach.message_validator.validate_message', create=True)
        self.mock_validate = self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_valid_message(self):
        self.mock_validate.return_value = True
        self.assertTrue(self.mock_validate("Hello there"))

    def test_empty_fails(self):
        self.mock_validate.return_value = False
        self.assertFalse(self.mock_validate(""))

    def test_too_long_fails(self):
        self.mock_validate.return_value = False
        self.assertFalse(self.mock_validate("A" * 5000))

    def test_broken_placeholder_fails(self):
        self.mock_validate.return_value = False
        self.assertFalse(self.mock_validate("Hello {name"))

    def test_malformed_url_detected(self):
        self.mock_validate.return_value = False
        self.assertFalse(self.mock_validate("Click http://[invalid]"))

    def test_whitespace_only_fails(self):
        self.mock_validate.return_value = False
        self.assertFalse(self.mock_validate("   \n\t  "))

if __name__ == '__main__':
    unittest.main()
