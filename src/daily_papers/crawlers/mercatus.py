import re
from typing import Optional

import requests
from bs4 import BeautifulSoup

from .base import BaseCrawler
from ..models import Paper


class MercatusCrawler(BaseCrawler):
    LIST_URL = "https://www.mercatus.org/research/working-papers"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
    }

    @property
    def source_name(self) -> str:
        return "Mercatus"

    @property
    def default_limit(self) -> int:
        return 50

    def fetch_papers(self, limit: int | None = None) -> list[Paper]:
        if limit is None:
            limit = self.default_limit
        try:
            resp = requests.get(self.LIST_URL, timeout=30, headers=self.HEADERS)
            if resp.status_code != 200:
                return []
            resp.encoding = "utf-8"
            soup = BeautifulSoup(resp.text, "html.parser")
            papers: list[Paper] = []

            for a in soup.find_all("a", href=True):
                href = a["href"]
                title = a.get_text(strip=True)
                if not title or len(title) < 20:
                    continue
                if "working-papers" not in href:
                    continue

                url = href if href.startswith("http") else f"https://www.mercatus.org{href}"

                published = ""
                for parent in a.parents:
                    time_tag = parent.find("time")
                    if time_tag and time_tag.get("datetime"):
                        published = time_tag["datetime"][:10]
                        break

                papers.append(Paper(
                    title=title,
                    authors=[],
                    published=published,
                    series="Mercatus Working Paper",
                    abstract="",
                    pdf_url="",
                    source=self.source_name,
                    url=url,
                ))
                if len(papers) >= limit:
                    break
            return papers
        except Exception:
            return []
