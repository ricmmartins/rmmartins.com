"""Check unlisted PDF pages after a production Hugo build."""

import base64
from html.parser import HTMLParser
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
DOCUMENTS = {
    "anthropic": ("anthropic.pdf", "ricardo-martins-anthropic.pdf"),
}


class DocumentParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.robots = set()
        self.download = None
        self.pdf_data = ""
        self.in_pdf_data = False
        self.links = set()
        self.ids = set()
        self.headings = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.add(attrs["id"])
        if tag == "a" and "href" in attrs:
            self.links.add(attrs["href"])
        if tag == "h3":
            self.headings += 1
        if tag == "meta" and attrs.get("name") == "robots":
            self.robots.update(attrs.get("content", "").replace(" ", "").split(","))
        if tag == "a" and attrs.get("id") == "download-pdf":
            self.download = attrs.get("download")
        if tag == "script" and attrs.get("id") == "pdf-data":
            self.in_pdf_data = True

    def handle_endtag(self, tag):
        if tag == "script":
            self.in_pdf_data = False

    def handle_data(self, data):
        if self.in_pdf_data:
            self.pdf_data += data


def check():
    for slug in ("nvidia", "nvis", "nvida"):
        assert not (PUBLIC / slug).exists(), f"Retired page still published: {slug}"
        assert not (PUBLIC / f"{slug}.html").exists(), slug
    for filename in ("nvis.pdf", "ricardo-nvidia.pdf"):
        assert not (ROOT / "assets" / "documents" / filename).exists(), filename
    page_paths = set()
    for slug, (filename, download_name) in DOCUMENTS.items():
        page = PUBLIC / slug / "index.html"
        page_paths.add(page)
        parser = DocumentParser()
        parser.feed(page.read_text(encoding="utf-8"))
        assert {"noindex", "nofollow", "nosnippet"} <= parser.robots, page
        assert parser.download == download_name, page
        embedded = base64.b64decode(parser.pdf_data.strip(), validate=True)
        assert embedded == (ROOT / "assets" / "documents" / filename).read_bytes(), page
        if slug == "anthropic":
            assert "project-context" in parser.ids, page
            assert parser.headings == 6, "Expected all six project descriptions"
            assert {
                "#project-context",
                "#resume",
                "https://rmmartins.com/projects",
                "https://decodifica.tech",
                "https://github.com/ricmmartins/azure-sre-agent-skills",
                "https://startupscalelanding.zone",
                "https://aksnewsletter.com",
                "https://azurefeed.news",
                "https://www.peerspect.app",
            } <= parser.links, "Missing project or navigation links"
        else:
            assert "project-context" not in parser.ids, page

    assert not list(PUBLIC.rglob("*.pdf")), "A standalone PDF was published"
    for name in ("sitemap.xml", "index.xml", "index.json", "robots.txt"):
        assert (PUBLIC / name).is_file(), f"Missing discovery surface: {name}"
    for path in PUBLIC.rglob("*"):
        if path.is_file() and path not in page_paths and path.suffix in {
            ".html", ".xml", ".json", ".txt"
        }:
            text = path.read_text(encoding="utf-8")
            for slug in DOCUMENTS:
                assert not re.search(
                    rf"(?<![\w./:-])(?:https://rmmartins\.com)?/{re.escape(slug)}(?:/|[\"'<>\s?#]|$)",
                    text,
                ), f"Unlisted URL exposed in {path}"
    print("Unlisted PDF pages: embedded bytes, noindex, and discovery exclusions OK")


if __name__ == "__main__":
    check()
