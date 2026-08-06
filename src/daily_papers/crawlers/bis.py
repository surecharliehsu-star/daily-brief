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
    "cb": "http://www.cbwiki.net/wiki/index.php/Specification_1.1",
    "dc": "http://purl.org/dc/elements/1.1/",
    "dcterms": "http://purl.org/dc/terms/",
    "content": "http://purl.org/rss/1.0/modules/content/",
}


class BISCrawler(BaseCrawler):
    FEED_URL = "https://www.bis.org/doclist/bis_fsi_publs.rss"

    @property
    def source_name(self) -> str:
        return "BIS"

    def fetch_papers(self, limit: int | None = None) -> list[Paper]:
        if limit is None:
            limit = self.default_limit
        resp = requests.get(self.FEED_URL, timeout=30)
        resp.encoding = "utf-8"
        root = ET.fromstring(resp.content)

        papers: list[Paper] = []
        items = root.findall(".//rss:item", NS)

        for item in items:
            publication = self._tag_text(item, "cb:publication")
            if "Working Papers" not in publication:
                continue
            paper = self._parse_item(item)
            if paper:
                papers.append(paper)
                if len(papers) >= limit:
                    break
        return papers

    def _parse_item(self, item) -> Optional[Paper]:
        title = self._tag_text(item, "rss:title")
        if not title:
            return None

        url = self._tag_text(item, "rss:link") or ""

        issue = self._tag_text(item, "cb:issue") or ""
        series = f"BIS WP No.{issue}" if issue else "BIS Working Paper"

        authors = self._tag_texts(item, "cb:byline")

        description = self._tag_text(item, "rss:description") or ""
        abstract = self._clean_abstract(description)

        pd = self._tag_text(item, "cb:publicationDate") or ""
        published = ""
        if pd:
            try:
                dt = datetime.strptime(pd, "%d %b %Y")
                published = dt.strftime("%Y-%m-%d")
            except ValueError:
                published = pd

        pdf_url = ""
        resource = item.find(".//cb:resource/cb:link", NS)
        if resource is not None and resource.text:
            pdf_url = resource.text.strip()

        topics: list[str] = []
        for kw_el in item.findall(".//cb:keyword", NS):
            if kw_el.text:
                topics.append(kw_el.text.strip())

        return Paper(
            title=title,
            authors=authors,
            published=published,
            series=series,
            abstract=abstract,
            pdf_url=pdf_url,
            source=self.source_name,
            url=url,
            topics=topics,
        )

    @staticmethod
    def _tag_text(item, path: str) -> str:
        el = item.find(f".//{{{NS[path.split(':')[0]]}}}{path.split(':')[1]}") if ":" in path else item.find(path)
        return el.text.strip() if el is not None and el.text else ""

    @staticmethod
    def _tag_texts(item, path: str) -> list[str]:
        ns_prefix, tag = path.split(":")
        els = item.findall(f".//{{{NS[ns_prefix]}}}{tag}")
        return [el.text.strip() for el in els if el is not None and el.text]

    @staticmethod
    def _clean_abstract(html_desc: str) -> str:
        text = re.sub(r"<br\s*/?>", " ", html_desc, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", "", text)
        text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&#8211;", "-").replace("&#8212;", "—")
        text = re.sub(r"\s+", " ", text).strip()
        text = re.sub(r"^by\s+.+?(?=\b(?:We|This|The|In|Our|I\s|It|An|A\s))", "", text)
        return text
