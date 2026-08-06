import feedparser
import html
import re
from datetime import datetime
from typing import Optional

from .base import BaseCrawler
from ..models import Paper


class FedCrawler(BaseCrawler):
    FEED_URL = "https://www.federalreserve.gov/feeds/feds.xml"

    @property
    def source_name(self) -> str:
        return "Federal Reserve Board"

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
        raw_title = entry.get("title", "").strip()
        if not raw_title:
            return None

        url = entry.get("link", "")
        title = raw_title.replace("FEDS Paper: ", "", 1).strip()

        summary = entry.get("summary", "")

        pdf_url = ""
        slug_match = re.search(r"/econres/feds/([^/]+)\.htm", url)
        if slug_match:
            slug = slug_match.group(1)
            pdf_url = f"https://www.federalreserve.gov/econres/feds/{slug}.pdf"

        published = ""
        if entry.get("published_parsed"):
            dt = datetime(*entry.published_parsed[:6])
            published = dt.strftime("%Y-%m-%d")

        authors, abstract = self._parse_summary(summary)

        return Paper(
            title=title,
            authors=authors,
            published=published,
            series="FEDS Paper",
            abstract=abstract,
            pdf_url=pdf_url,
            source=self.source_name,
            url=url,
        )

    @staticmethod
    def _parse_summary(html_str: str) -> tuple[list[str], str]:
        html_str = html_str.replace("&amp;", "&")
        text = re.sub(r"<br\s*/?>", "\n", html_str, flags=re.IGNORECASE)
        lines = [l.strip() for l in text.split("\n") if l.strip()]

        authors: list[str] = []
        abstract = ""

        if lines:
            linked = re.findall(r">([^<]+)</a>", lines[0])
            if linked:
                authors = [html.unescape(l.strip()) for l in linked if l.strip()]
                remaining = re.sub(r"<[^>]+>", "", lines[0])
                for a in authors:
                    remaining = remaining.replace(a, "", 1)
                remaining = remaining.strip().strip(",").strip()
                if remaining:
                    extra = [html.unescape(e.strip()) for e in remaining.split(",") if e.strip()]
                    for e in extra:
                        if e.lower() != "and" and e not in authors:
                            authors.append(e)
            else:
                raw = re.sub(r"<[^>]+>", "", lines[0]).strip()
                parts = [html.unescape(p.strip()) for p in raw.split(",") if p.strip()]
                authors = [p for p in parts if p.lower() != "and"]

            if len(lines) > 1:
                abstract = re.sub(r"<[^>]+>", "", "\n".join(lines[1:])).strip()

        authors = [a for a in authors if a.lower() != "and"]
        abstract = re.sub(r"\s+", " ", abstract).strip()
        return authors, abstract
