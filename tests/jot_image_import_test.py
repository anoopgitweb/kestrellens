import unittest
from unittest.mock import patch

import app


class JotImageImportSafetyTest(unittest.TestCase):
    def test_rejects_local_and_private_hosts(self):
        with self.assertRaises(ValueError):
            app._assert_public_image_url("http://127.0.0.1/private.png")
        with patch("app.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("10.0.0.5", 443))]):
            with self.assertRaises(ValueError):
                app._assert_public_image_url("https://example.test/private.png")

    def test_accepts_public_http_image_url(self):
        with patch("app.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]):
            self.assertEqual(
                app._assert_public_image_url("https://example.com/image.png"),
                "https://example.com/image.png",
            )


if __name__ == "__main__":
    unittest.main()
