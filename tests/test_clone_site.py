"""Tests for clone_site.py using a local HTTP server (no external network needed)."""
import http.server
import os
import shutil
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import clone_site  # noqa: E402

FIXTURE_FILES = {
    "/index.html": """<!doctype html>
<html>
<head>
  <link rel="stylesheet" href="/css/style.css">
</head>
<body>
  <img src="/images/logo.png">
  <script src="/js/app.js"></script>
  <a href="/about.html">About</a>
</body>
</html>
""",
    "/about.html": """<!doctype html>
<html>
<head><title>About</title></head>
<body><p>About page</p></body>
</html>
""",
    "/css/style.css": "body { background: url('../images/bg.png'); }\n",
    "/js/app.js": "console.log('hello');\n",
    "/images/logo.png": "\x89PNG-fake-logo-bytes",
    "/images/bg.png": "\x89PNG-fake-bg-bytes",
}


class FixtureHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 (stdlib naming)
        body = FIXTURE_FILES.get(self.path)
        if body is None:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        if self.path.endswith(".css"):
            self.send_header("Content-Type", "text/css")
        elif self.path.endswith(".js"):
            self.send_header("Content-Type", "application/javascript")
        elif self.path.endswith(".png"):
            self.send_header("Content-Type", "image/png")
        else:
            self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(body.encode("latin-1"))

    def log_message(self, format, *args):  # silence test server logging
        pass


class CloneSiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.HTTPServer(("127.0.0.1", 0), FixtureHandler)
        cls.port = cls.server.server_port
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.out_dir = tempfile.mkdtemp(prefix="clone_site_test_")

    def tearDown(self):
        shutil.rmtree(self.out_dir, ignore_errors=True)

    def base_url(self, path="/index.html"):
        return f"http://127.0.0.1:{self.port}{path}"

    def test_clones_single_page_and_assets(self):
        saved = clone_site.clone_site(self.base_url(), self.out_dir)
        self.assertEqual(len(saved), 1)

        html_path = saved[0]
        self.assertTrue(os.path.isfile(html_path))
        with open(html_path, encoding="utf-8") as fh:
            html = fh.read()

        # Assets should have been downloaded to disk.
        css_path = os.path.join(self.out_dir, "127.0.0.1:%d" % self.port, "css", "style.css")
        js_path = os.path.join(self.out_dir, "127.0.0.1:%d" % self.port, "js", "app.js")
        img_path = os.path.join(self.out_dir, "127.0.0.1:%d" % self.port, "images", "logo.png")
        self.assertTrue(os.path.isfile(css_path))
        self.assertTrue(os.path.isfile(js_path))
        self.assertTrue(os.path.isfile(img_path))

        # And the HTML should reference them via relative paths, not the
        # original absolute URLs.
        self.assertNotIn(f"http://127.0.0.1:{self.port}", html)
        self.assertIn("css/style.css", html)
        self.assertIn("js/app.js", html)
        self.assertIn("images/logo.png", html)

    def test_css_url_references_are_rewritten(self):
        clone_site.clone_site(self.base_url(), self.out_dir)
        css_path = os.path.join(self.out_dir, "127.0.0.1:%d" % self.port, "css", "style.css")
        with open(css_path, encoding="utf-8") as fh:
            css = fh.read()
        self.assertNotIn(f"http://127.0.0.1:{self.port}", css)
        self.assertIn("bg.png", css)
        bg_path = os.path.join(self.out_dir, "127.0.0.1:%d" % self.port, "images", "bg.png")
        self.assertTrue(os.path.isfile(bg_path))

    def test_follow_links_clones_linked_pages(self):
        saved = clone_site.clone_site(
            self.base_url(), self.out_dir, follow_links=True, max_pages=5
        )
        self.assertEqual(len(saved), 2)
        about_path = os.path.join(self.out_dir, "127.0.0.1:%d" % self.port, "about.html")
        self.assertTrue(os.path.isfile(about_path))

    def test_missing_page_returns_empty(self):
        saved = clone_site.clone_site(self.base_url("/does-not-exist.html"), self.out_dir)
        self.assertEqual(saved, [])


if __name__ == "__main__":
    unittest.main()
