import re
from datetime import datetime
from typing import Optional

import requests

from .base import BaseCrawler
from ..models import Paper


class WorldBankCrawler(BaseCrawler):
    API_URL = "https://search.worldbank.org/api/v2/wds"

    @property
    def source_name(self) -> str:
        return "World Bank"

    def fetch_papers(self, limit: int | None = None) -> list[Paper]:
        if limit is None:
            limit = self.default_limit
        resp = requests.get(self.API_URL, params={
            "format": "json",
            "rows": limit,
            "docty": "Working Paper",
            "sort": "docdt desc",
        }, timeout=30)
        data = resp.json()
        papers: list[Paper] = []
        for doc in data.get("documents", {}).values():
            paper = self._parse_doc(doc)
            if paper:
                papers.append(paper)
        return papers

    def _parse_doc(self, doc: dict) -> Optional[Paper]:
        docna = doc.get("docna", {})
        title = ""
        if isinstance(docna, dict):
            for v in docna.values():
                if isinstance(v, dict) and v.get("docna"):
                    title = v["docna"].strip()
                    break
        title = re.sub(r"\s+", " ", title).strip()
        if not title:
            return None

        docdt = doc.get("docdt", "")
        published = ""
        if docdt:
            try:
                dt = datetime.fromisoformat(docdt.replace("Z", ""))
                published = dt.strftime("%Y-%m-%d")
            except ValueError:
                published = docdt[:10]

        authors_raw = doc.get("authors", {})
        authors: list[str] = []
        if isinstance(authors_raw, dict):
            for v in authors_raw.values():
                if isinstance(v, dict) and v.get("author"):
                    authors.append(v["author"].strip())

        abstracts = doc.get("abstracts", {})
        abstract = ""
        if isinstance(abstracts, dict):
            for v in abstracts.values():
                if isinstance(v, str) and v.strip():
                    abstract = v.strip()
                    break

        pdf_url = doc.get("pdfurl", "")
        url = doc.get("pdfurl", "") or doc.get("url", "")

        return Paper(
            title=title,
            authors=authors,
            published=published,
            series="World Bank Working Paper",
            abstract=abstract,
            pdf_url=pdf_url,
            source=self.source_name,
            url=url,
        )
