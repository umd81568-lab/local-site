#!/usr/bin/env python3
"""clone_site.py - Copy the static front-end files of any website link.

This is a small home-lab learning tool: point it at a URL and it will
download the page's HTML plus any linked CSS, JavaScript, images and
fonts into a local folder, rewriting the references so the copy works
completely offline (no database involved). The resulting folder can be
dropped straight into an Apache/XAMPP ``htdocs`` directory, or served
with any static "live server" such as ``python -m http.server`` or
``npx live-server``.

Usage:
    python3 clone_site.py https://example.com -o output
    python3 clone_site.py https://example.com -o output --follow-links --max-pages 5

Only static, publicly reachable assets are copied. Pages that require a
login, JavaScript-rendered content, or a backend database are outside
the scope of this simple tool.
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import deque
from typing import Optional
from urllib.parse import urljoin, urlparse, urlsplit

import requests
from bs4 import BeautifulSoup

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; clone_site.py/1.0; "
        "+https://github.com/) home-lab learning tool"
    )
}

# HTML tag -> attribute holding the asset URL we should download.
ASSET_ATTRS = [
    ("link", "href"),
    ("script", "src"),
    ("img", "src"),
    ("source", "src"),
    ("audio", "src"),
    ("video", "src"),
]


def is_downloadable_url(url: str) -> bool:
    """Return True for http(s) URLs we can actually fetch."""
    if not url:
        return False
    if url.startswith(("data:", "mailto:", "tel:", "javascript:", "#")):
        return False
    scheme = urlparse(url).scheme
    return scheme in ("", "http", "https")


def local_path_for(url: str, out_dir: str) -> str:
    """Compute a filesystem path under out_dir for a given absolute URL."""
    parsed = urlsplit(url)
    path = parsed.path or "/"
    if path.endswith("/"):
        path += "index.html"
    # Strip leading slash so os.path.join behaves.
    rel = os.path.join(parsed.netloc, path.lstrip("/"))
    return os.path.normpath(os.path.join(out_dir, rel))


def relative_link(from_file: str, to_file: str) -> str:
    """Return a relative path from from_file's directory to to_file."""
    rel = os.path.relpath(to_file, start=os.path.dirname(from_file))
    return rel.replace(os.sep, "/")


class SiteCloner:
    def __init__(self, out_dir: str, session: Optional[requests.Session] = None,
                 timeout: int = 15):
        self.out_dir = out_dir
        self.session = session or requests.Session()
        self.timeout = timeout
        # Maps an absolute asset URL to the local file path it was saved to.
        self.downloaded: dict[str, str] = {}

    def fetch(self, url: str) -> Optional[requests.Response]:
        try:
            resp = self.session.get(url, headers=DEFAULT_HEADERS, timeout=self.timeout)
            resp.raise_for_status()
            return resp
        except requests.RequestException as exc:
            print(f"  ! failed to download {url}: {exc}", file=sys.stderr)
            return None

    def save_asset(self, url: str) -> Optional[str]:
        """Download a non-HTML asset (css/js/img/...) and return its local path."""
        if url in self.downloaded:
            return self.downloaded[url]
        resp = self.fetch(url)
        if resp is None:
            return None
        dest = local_path_for(url, self.out_dir)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as fh:
            fh.write(resp.content)
        self.downloaded[url] = dest
        print(f"  + {url} -> {os.path.relpath(dest, self.out_dir)}")

        # CSS files may reference further assets (fonts, images) via url(...).
        content_type = resp.headers.get("Content-Type", "")
        if "css" in content_type or url.endswith(".css"):
            self._download_css_assets(url, resp.text, dest)
        return dest

    def _download_css_assets(self, css_url: str, css_text: str, css_dest: str) -> None:
        import re

        for match in re.finditer(r"url\(\s*['\"]?([^'\")]+)['\"]?\s*\)", css_text):
            ref = match.group(1)
            if not is_downloadable_url(ref):
                continue
            abs_url = urljoin(css_url, ref)
            asset_dest = self.save_asset(abs_url)
            if asset_dest:
                rel = relative_link(css_dest, asset_dest)
                css_text = css_text.replace(match.group(1), rel)
        with open(css_dest, "w", encoding="utf-8", errors="ignore") as fh:
            fh.write(css_text)

    def clone_page(self, url: str) -> Optional[str]:
        """Download a single HTML page, rewrite asset links, and return its local path."""
        resp = self.fetch(url)
        if resp is None:
            return None

        dest = local_path_for(url, self.out_dir)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        self.downloaded[url] = dest

        soup = BeautifulSoup(resp.text, "html.parser")

        for tag_name, attr in ASSET_ATTRS:
            for tag in soup.find_all(tag_name):
                src = tag.get(attr)
                if not is_downloadable_url(src):
                    continue
                abs_url = urljoin(url, src)
                asset_dest = self.save_asset(abs_url)
                if asset_dest:
                    tag[attr] = relative_link(dest, asset_dest)

        with open(dest, "w", encoding="utf-8", errors="ignore") as fh:
            fh.write(str(soup))
        print(f"* {url} -> {os.path.relpath(dest, self.out_dir)}")
        return dest

    def page_links(self, url: str, html: str) -> list[str]:
        """Return same-origin page links found in an HTML document."""
        soup = BeautifulSoup(html, "html.parser")
        origin = urlparse(url)
        links = []
        for tag in soup.find_all("a"):
            href = tag.get("href")
            if not is_downloadable_url(href):
                continue
            abs_url = urljoin(url, href).split("#")[0]
            if urlparse(abs_url).netloc == origin.netloc:
                links.append(abs_url)
        return links


def clone_site(start_url: str, out_dir: str, follow_links: bool = False,
                max_pages: int = 1) -> list[str]:
    """Clone one or more pages of a site into out_dir. Returns saved page paths."""
    os.makedirs(out_dir, exist_ok=True)
    cloner = SiteCloner(out_dir)

    saved_pages = []
    visited = set()
    queue = deque([start_url])

    while queue and len(visited) < max_pages:
        url = queue.popleft()
        if url in visited:
            continue
        visited.add(url)

        resp = cloner.fetch(url)
        if resp is None:
            continue

        dest = cloner.clone_page(url)
        if dest:
            saved_pages.append(dest)

        if follow_links and len(visited) < max_pages:
            for link in cloner.page_links(url, resp.text):
                if link not in visited:
                    queue.append(link)

    return saved_pages


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Copy any website's static HTML/CSS/JS/images to a local folder "
                    "(no database) for offline learning with XAMPP or a live server.",
    )
    parser.add_argument("url", help="The site link to clone, e.g. https://example.com")
    parser.add_argument("-o", "--output", default="output",
                         help="Output folder (default: ./output)")
    parser.add_argument("--follow-links", action="store_true",
                         help="Also clone same-site pages linked from the start page")
    parser.add_argument("--max-pages", type=int, default=1,
                         help="Maximum number of pages to clone when following links "
                              "(default: 1)")
    args = parser.parse_args(argv)

    saved = clone_site(args.url, args.output, follow_links=args.follow_links,
                        max_pages=args.max_pages)
    if not saved:
        print("No pages were downloaded.", file=sys.stderr)
        return 1

    print(f"\nDone. {len(saved)} page(s) saved under '{args.output}'.")
    print("Serve it locally with, for example:")
    print(f"  cd {args.output} && python3 -m http.server 8000")
    print("...or copy the folder into your XAMPP 'htdocs' directory.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
