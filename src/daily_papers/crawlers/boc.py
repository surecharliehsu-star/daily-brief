import re
from datetime import datetime
from typing import Optional
from xml.etree import ElementTree as ET

import requests

from .base import BaseCrawler
from ..models import Paper

NS = {
    "rss": "http://purl.org/rss/1.0/",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "dc": "http://purl.org/dc/elements/1.1/",
    "dcterms": "http://purl.org/dc/terms/",
    "cb": "http://www.cbwiki.net/wiki/index.php/Specification_1.2/",
}


class BOCCrawler(BaseCrawler):
    FEED_URL = "https://www.bankofcanada.ca/content_type/working-papers/feed/"

    @property
    def source_name(self) -> str:
        return "Bank of Canada"

    def fetch_papers(self, limit: int | None = None) -> list[Paper]:
        if limit is None:
            limit = self.default_limit
        resp = requests.get(self.FEED_URL, timeout=30)
        resp.encoding = "utf-8"
        root = ET.fromstring(resp.content)
        papers: list[Paper] = []
        items = root.findall(".//rss:item", NS)
        for item in items:
            paper = self._parse_item(item)
            if paper:
                papers.append(paper)
                if len(papers) >= limit:
                    break
        return papers

    def _parse_item(self, item) -> Optional[Paper]:
        title = self._tag_text(item, "dc:title") or self._tag_text(item, "rss:title")
        if not title:
            return None

        url = self._tag_text(item, "rss:link") or ""

        description = self._tag_text(item, "rss:description") or ""
        abstract = self._clean_html(description)

        pd = self._tag_text(item, "dc:date")
        published = ""
        if pd:
            try:
                dt = datetime.fromisoformat(pd.replace("Z", "+00:00"))
                published = dt.strftime("%Y-%m-%d")
            except ValueError:
                published = pd[:10]

        pdf_url = ""
        resource = item.find(".//cb:resource/cb:link", NS)
        if resource is not None and resource.text:
            pdf_url = resource.text.strip()

        authors: list[str] = []
        for el in item.findall(".//dc:creator", NS):
            if el.text:
                authors.append(el.text.strip())

        return Paper(
            title=title,
            authors=authors,
            published=published,
            series="Bank of Canada Staff Working Paper",
            abstract=abstract,
            pdf_url=pdf_url,
            source=self.source_name,
            url=url,
        )

    @staticmethod
    def _tag_text(item, path: str) -> str:
        ns_prefix, tag = path.split(":")
        el = item.find(f".//{{{NS[ns_prefix]}}}{tag}")
        return el.text.strip() if el is not None and el.text else ""

    @staticmethod
    def _clean_html(text: str) -> str:
        text = re.sub(r"<[^>]+>", "", text)
        text = text.replace("&nbsp;", " ").replace("&amp;", "&")
        text = re.sub(r"\s+", " ", text).strip()
        return text
