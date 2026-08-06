import re
from datetime import datetime
from typing import Optional

import requests
from bs4 import BeautifulSoup

from .base import BaseCrawler
from ..models import Paper

MONTHS = r"(January|February|March|April|May|June|July|August|September|October|November|December)"
DATE_PATTERN = re.compile(r"(\d{1,2})\s*" + MONTHS + r"\s*(\d{4})")


class HKMACrawler(BaseCrawler):
    LIST_URL = "https://www.hkma.gov.hk/eng/data-publications-and-research/research/research-memorandums/"

    @property
    def source_name(self) -> str:
        return "HKMA"

    @property
    def default_limit(self) -> int:
        return 50

    @staticmethod
    def _parse_date(text: str) -> tuple[str, bool]:
        m = DATE_PATTERN.search(text)
        if m:
            try:
                dt = datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%d %B %Y")
                return dt.strftime("%Y-%m-%d"), False
            except ValueError:
                pass
        return "", True

    def fetch_papers(self, limit: int | None = None) -> list[Paper]:
        if limit is None:
            limit = self.default_limit
        try:
            resp = requests.get(self.LIST_URL, timeout=30)
            resp.encoding = "utf-8"
            soup = BeautifulSoup(resp.text, "html.parser")
            papers: list[Paper] = []
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if not href.endswith(".pdf"):
                    continue
                title = a.get_text(strip=True)
                if not title:
                    continue
                title = re.sub(r"^Research\s+Memorandum\s*[-–]\s*\d{4}/\d{2}\s*", "", title).strip()
                title = re.sub(r"^\d{4}/\d{2}\s*", "", title).strip()

                parent = a.find_parent(["li", "div", "p", "td", "section", "span"])
                container_text = parent.get_text(strip=True) if parent else ""
                published, date_estimated = self._parse_date(container_text)

                pdf_url = href if href.startswith("http") else f"https://www.hkma.gov.hk{href}"
                papers.append(Paper(
                    title=title,
                    authors=[],
                    published=published,
                    series="HKMA Research Memorandum",
                    abstract="",
                    pdf_url=pdf_url,
                    source=self.source_name,
                    url=pdf_url,
                    date_estimated=date_estimated,
                ))
                if len(papers) >= limit:
                    break
            return papers
        except Exception:
            return []
