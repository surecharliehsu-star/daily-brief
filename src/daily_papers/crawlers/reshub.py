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
    "content": "http://purl.org/rss/1.0/modules/content/",
    "cb": "http://www.cbwiki.net/wiki/index.php/Specification_1.1",
}


class ResHubCrawler(BaseCrawler):
    FEED_URL = "https://www.bis.org/doclist/reshub_papers.rss"

    @property
    def source_name(self) -> str:
        return "BIS Research Hub"

    def fetch_papers(self, limit: int | None = None) -> list[Paper]:
        if limit is None:
            limit = self.default_limit
        resp = requests.get(self.FEED_URL, timeout=30)
        resp.encoding = "utf-8"
        root = ET.fromstring(resp.content)
        papers: list[Paper] = []
        for item in root.findall(".//rss:item", NS):
            paper = self._parse_item(item)
            if paper:
                papers.append(paper)
                if len(papers) >= limit:
                    break
        return papers

    def _parse_item(self, item) -> Optional[Paper]:
        title = (self._tag_text(item, "cb:simpleTitle")
                 or self._tag_text(item, "dc:title")
                 or self._tag_text(item, "rss:title"))
        if not title:
            return None

        url = self._tag_text(item, "rss:link") or ""

        description = self._tag_text(item, "rss:description") or ""
        abstract_text = self._tag_text(item, "dcterms:abstract") or ""
        abstract = abstract_text or self._clean_html(description)
        institution = self._extract_institution(description, url)

        pd = self._tag_text(item, "dc:date")
        published = ""
        if pd:
            try:
                dt = datetime.fromisoformat(pd.replace("Z", "+00:00").replace("T", " "))
                if dt <= datetime.now(dt.tzinfo):
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
            series=institution,
            abstract=abstract,
            pdf_url=pdf_url,
            source=self.source_name,
            url=url,
        )

    @staticmethod
    def _extract_institution(description: str, url: str) -> str:
        mapping = {
            "federalreserve.gov": "Federal Reserve Board",
            "philadelphiafed.org": "Philadelphia Fed",
            "kansascityfed.org": "Kansas City Fed",
            "frbsf.org": "San Francisco Fed",
            "atlantafed.org": "Atlanta Fed",
            "clevelandfed.org": "Cleveland Fed",
            "dallasfed.org": "Dallas Fed",
            "stlouisfed.org": "St. Louis Fed",
            "richmondfed.org": "Richmond Fed",
            "chicagofed.org": "Chicago Fed",
            "bostonfed.org": "Boston Fed",
            "minneapolisfed.org": "Minneapolis Fed",
            "newyorkfed.org": "New York Fed",
            "bde.es": "Bank of Spain",
            "rba.gov.au": "Reserve Bank of Australia",
            "bis.org": "BIS",
            "imf.org": "IMF",
            "oecd.org": "OECD",
            "bankofcanada.ca": "Bank of Canada",
            "bankofengland.co.uk": "Bank of England",
            "ecb.europa.eu": "ECB",
            "boj.or.jp": "Bank of Japan",
            "nber.org": "NBER",
            "cepii.fr": "CEPII",
        }
        for domain, name in mapping.items():
            if domain in url:
                return name

        desc_match = re.search(r"by\s+(.+?)(?:\s+Working|\s+Paper|\s+Staff|\s+Research|\s+\d{4})", description)
        if desc_match:
            return desc_match.group(1).strip()
        return "BIS Research Hub"

    @staticmethod
    def _tag_text(item, path: str) -> str:
        if ":" in path:
            ns_prefix, tag = path.split(":")
            el = item.find(f".//{{{NS[ns_prefix]}}}{tag}")
        else:
            el = item.find(path)
        return el.text.strip() if el is not None and el.text else ""

    @staticmethod
    def _clean_html(text: str) -> str:
        text = re.sub(r"<[^>]+>", "", text)
        text = text.replace("&nbsp;", " ").replace("&amp;", "&")
        text = re.sub(r"\s+", " ", text).strip()
        return text
