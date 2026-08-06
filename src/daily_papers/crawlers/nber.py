import feedparser
import re
from datetime import datetime
from typing import Optional

from .base import BaseCrawler
from ..models import Paper


class NBERCrawler(BaseCrawler):
    FEED_URL = "https://back.nber.org/rss/new.xml"

    @property
    def source_name(self) -> str:
        return "NBER"

    def fetch_papers(self, limit: int | None = None) -> list[Paper]:
        if limit is None:
            limit = self.default_limit
        feed = feedparser.parse(self.FEED_URL)
        papers: list[Paper] = []
        for entry in feed.entries:
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

        url = entry.get("link", "").split("#")[0]

        wp_id = ""
        id_match = re.search(r"/w(\d{5})", url)
        if id_match:
            wp_id = id_match.group(1)
        series = f"NBER WP No.{wp_id}" if wp_id else "NBER Working Paper"

        authors, clean_title = self._parse_title_authors(title)

        summary = entry.get("summary", "")
        abstract = self._clean_html(summary)

        published = ""
        if entry.get("published_parsed"):
            dt = datetime(*entry.published_parsed[:6])
            published = dt.strftime("%Y-%m-%d")
        elif entry.get("updated_parsed"):
            dt = datetime(*entry.updated_parsed[:6])
            published = dt.strftime("%Y-%m-%d")

        pdf_url = f"https://www.nber.org/system/files/working_papers/w{wp_id}/w{wp_id}.pdf" if wp_id else ""

        return Paper(
            title=clean_title,
            authors=authors,
            published=published,
            series=series,
            abstract=abstract,
            pdf_url=pdf_url,
            source=self.source_name,
            url=url,
        )

    @staticmethod
    def _parse_title_authors(raw_title: str) -> tuple[list[str], str]:
        parts = raw_title.split(" -- by ", 1)
        if len(parts) == 2:
            title = parts[0].strip()
            raw_authors = parts[1].strip()
            authors = [a.strip() for a in raw_authors.split(",")]
            return authors, title
        return [], raw_title

    @staticmethod
    def _clean_html(text: str) -> str:
        text = re.sub(r"<[^>]+>", "", text)
        text = text.replace("&nbsp;", " ").replace("&amp;", "&")
        text = re.sub(r"\s+", " ", text).strip()
        return text
