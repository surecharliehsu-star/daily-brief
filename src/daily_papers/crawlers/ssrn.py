from typing import Optional

import requests

from .base import BaseCrawler
from ..models import Paper

OPENALEX_SSRN = (
    "https://api.openalex.org/works"
    "?filter=primary_location.source.id:https://openalex.org/S4210172589"
    ",concepts.id:C162324750"
    "&sort=publication_date:desc"
)


class SSRNCrawler(BaseCrawler):
    @property
    def source_name(self) -> str:
        return "SSRN"

    def fetch_papers(self, limit: int | None = None) -> list[Paper]:
        if limit is None:
            limit = self.default_limit
        try:
            resp = requests.get(f"{OPENALEX_SSRN}&per_page={limit}", timeout=30)
            data = resp.json()
            papers: list[Paper] = []
            for work in data.get("results", []):
                paper = self._parse_work(work)
                if paper:
                    papers.append(paper)
            return papers
        except Exception:
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

        loc = work.get("primary_location") or {}
        pdf_url = loc.get("pdf_url") or ""

        return Paper(
            title=title,
            authors=authors,
            published=published,
            series="SSRN Working Paper",
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
