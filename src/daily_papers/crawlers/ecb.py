import re
from datetime import datetime
from typing import Optional

import feedparser

from .base import BaseCrawler
from ..models import Paper


class ECDCrawler(BaseCrawler):
    FEED_URL = "https://www.ecb.europa.eu/rss/wppub.rss"

    @property
    def source_name(self) -> str:
        return "ECB"

    def fetch_papers(self, limit: int | None = None) -> list[Paper]:
        if limit is None:
            limit = self.default_limit
        feed = feedparser.parse(self.FEED_URL)
        papers: list[Paper] = []
        for entry in feed.entries:
            link = entry.get("link", "")
            if not re.search(r"/pub/pdf/scpwps/|/pub/pdf/scpdps/", link):
                continue
            paper = self._parse_entry(entry)
            if paper:
                papers.append(paper)
                if len(papers) >= limit:
                    break
        return papers

    def _parse_entry(self, entry) -> Optional[Paper]:
        title = entry.get("title", "").strip()
        if not title:
            return None

        url = entry.get("link", "")

        wp_match = re.search(r"ecb\.(wp|dp)(\d+)", url)
        series = ""
        if wp_match:
            prefix = "WP" if wp_match.group(1) == "wp" else "DP"
            series = f"ECB {prefix} No.{wp_match.group(2)}"

        summary = entry.get("summary", "")

        published = ""
        if entry.get("published_parsed"):
            dt = datetime(*entry.published_parsed[:6])
            published = dt.strftime("%Y-%m-%d")

        pdf_url = url if url.endswith(".pdf") else ""

        return Paper(
            title=title,
            authors=[],
            published=published,
            series=series,
            abstract=self._clean_html(summary),
            pdf_url=pdf_url,
            source=self.source_name,
            url=url,
        )

    @staticmethod
    def _clean_html(text: str) -> str:
        text = re.sub(r"<[^>]+>", "", text)
        text = text.replace("&nbsp;", " ").replace("&amp;", "&")
        text = re.sub(r"\s+", " ", text).strip()
        return text
