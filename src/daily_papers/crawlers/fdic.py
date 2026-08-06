import time
from typing import Optional

import requests

from .base import BaseCrawler
from ..models import Paper

MAX_RETRIES = 3
RETRY_BACKOFF = [0.5, 1.0, 2.0]

OPENALEX_FDIC = (
    "https://api.openalex.org/works"
    "?filter=authorships.institutions.id:https://openalex.org/I1320395740"
    "&sort=publication_date:desc"
)


class FDICCrawler(BaseCrawler):
    @property
    def source_name(self) -> str:
        return "FDIC"

    def fetch_papers(self, limit: int | None = None) -> list[Paper]:
        if limit is None:
            limit = self.default_limit
        resp = None
        last_err = None
        for attempt in range(MAX_RETRIES):
            try:
                resp = requests.get(f"{OPENALEX_FDIC}&per_page={limit}", timeout=30)
                if resp.status_code == 200:
                    break
                last_err = f"HTTP {resp.status_code}"
            except Exception as e:
                last_err = str(e)
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)])
        if resp is None or resp.status_code != 200:
            print(f"  [WARN] FDIC fetch failed after {MAX_RETRIES} attempts: {last_err}")
            return []
        try:
            data = resp.json()
            papers: list[Paper] = []
            for work in data.get("results", []):
                paper = self._parse_work(work)
                if paper:
                    papers.append(paper)
            return papers
        except Exception as e:
            print(f"  [WARN] FDIC parse failed: {e}")
            return []

    def _parse_work(self, work: dict) -> Optional[Paper]:
        title = work.get("title") or ""
        if not title:
            return None

        published = (work.get("publication_date") or "")[:10]

        authors: list[str] = []
        for a in work.get("authorships", []):
            name = a.get("author", {}).get("display_name", "")
            if name:
                authors.append(name)

        inverted = work.get("abstract_inverted_index") or {}
        abstract = self._reconstruct_abstract(inverted)

        doi = work.get("doi") or ""
        url = doi or ""
        pdf_url = ""

        return Paper(
            title=title,
            authors=authors,
            published=published,
            series="FDIC Research Paper",
            abstract=abstract,
            pdf_url=pdf_url,
            source=self.source_name,
            url=url,
        )

    @staticmethod
    def _reconstruct_abstract(inverted: dict) -> str:
        if not inverted:
            return ""
        items = [(pos, word) for word, positions in inverted.items() for pos in positions]
        items.sort()
        return " ".join(word for _, word in items)
