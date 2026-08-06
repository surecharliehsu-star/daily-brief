import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Optional

import requests
from bs4 import BeautifulSoup

from .base import BaseCrawler
from ..models import Paper

MONTH_MAP = {
    "jan": 1, "jan.": 1, "feb": 2, "feb.": 2, "mar": 3, "mar.": 3,
    "apr": 4, "apr.": 4, "may": 5, "may.": 5, "jun": 6, "jun.": 6,
    "jul": 7, "jul.": 7, "aug": 8, "aug.": 8, "sep": 9, "sep.": 9,
    "oct": 10, "oct.": 10, "nov": 11, "nov.": 11, "dec": 12, "dec.": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}

MAX_RETRIES = 3
RETRY_BACKOFF = [0.5, 1.0, 2.0]
DETAIL_WINDOW_DAYS = 40
DETAIL_TOP_N = 3
DETAIL_WORKERS = 8

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"


def _parse_boj_date(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    m = re.match(r"([A-Za-z.]+)\s+(\d{1,2}),\s*(\d{4})", text)
    if not m:
        return ""
    month_str = m.group(1).lower().strip(".")
    month = MONTH_MAP.get(month_str)
    if not month:
        return ""
    return f"{m.group(3)}-{month:02d}-{int(m.group(2)):02d}"


def _get_with_retry(url: str, timeout: int = 30) -> Optional[requests.Response]:
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, timeout=timeout, headers={"User-Agent": _UA})
            if resp.status_code == 200:
                return resp
        except Exception:
            pass
        if attempt < MAX_RETRIES - 1:
            time.sleep(RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)])
    return None


def _parse_detail_page(url: str) -> dict:
    resp = _get_with_retry(url)
    if resp is None:
        return {"abstract": "", "pdf_url": "", "reason": "抓取失败"}
    try:
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception:
        return {"abstract": "", "pdf_url": "", "reason": "抓取失败"}

    abstract = ""
    for kw in ("Abstract", "概要", "Summary"):
        node = soup.find(string=re.compile(rf"^\s*{kw}\s*$"))
        if node:
            parent = node.find_parent()
            for sib in parent.next_siblings:
                if getattr(sib, "name", None) in ("p", "div", "td"):
                    txt = re.sub(r"\s+", " ", sib.get_text(" ", strip=True))
                    if txt:
                        abstract = txt
                        break
            if abstract:
                break

    pdf_url = ""
    full_text = soup.find("a", href=re.compile(r"\.pdf", re.I))
    if full_text and full_text.get("href"):
        href = full_text["href"]
        pdf_url = href if href.startswith("http") else f"https://www.boj.or.jp{href}"

    if not abstract:
        return {"abstract": "", "pdf_url": pdf_url, "reason": "无英文摘要"}
    return {"abstract": abstract, "pdf_url": pdf_url, "reason": ""}


class BOJCrawler(BaseCrawler):
    LIST_URL = "https://www.boj.or.jp/en/research/rs_all_2026/index.htm"

    @property
    def source_name(self) -> str:
        return "Bank of Japan"

    @property
    def default_limit(self) -> int:
        return 50

    def fetch_papers(self, limit: int | None = None) -> list[Paper]:
        if limit is None:
            limit = self.default_limit

        soup = _parse_list(self.LIST_URL)
        if soup is None:
            return []

        all_papers = _parse_list_rows(soup)
        all_papers.sort(key=lambda p: p["published"], reverse=True)
        kept = all_papers[:limit]

        _enrich_detail(kept)

        results = []
        for p in kept:
            paper = Paper(
                title=p["title"],
                authors=p["authors"],
                published=p["published"],
                series=p["series"],
                abstract=p["abstract"],
                pdf_url=p["pdf_url"],
                source=self.source_name,
                url=p["url"],
            )
            if p.get("reason"):
                paper.abstract_missing_reason = p["reason"]
            results.append(paper)
        return results


def _parse_list(url: str) -> Optional[BeautifulSoup]:
    resp = _get_with_retry(url)
    if resp is None:
        return None
    try:
        resp.encoding = "utf-8"
        return BeautifulSoup(resp.text, "html.parser")
    except Exception:
        return None


def _parse_list_rows(soup: BeautifulSoup) -> list[dict]:
    out = []
    for table in soup.find_all("table"):
        for row in table.find_all("tr")[1:]:
            cells = row.find_all("td")
            if len(cells) < 3:
                continue
            date_raw = cells[0].get_text(strip=True)
            published = _parse_boj_date(date_raw)
            if not published:
                continue
            author_raw = cells[1].get_text(strip=True)
            title_cell = cells[2]
            title = title_cell.get_text(strip=True)
            title = re.sub(r"\s*\[PDF\s*\d*KB?\]\s*$", "", title).strip()
            if not title or len(title) < 5:
                continue
            link_tag = title_cell.find("a")
            link = ""
            if link_tag and link_tag.get("href"):
                href = link_tag["href"]
                link = href if href.startswith("http") else f"https://www.boj.or.jp{href}"
            pdf_url = ""
            if link and link.endswith(".pdf"):
                pdf_url = link
            authors = [a.strip() for a in author_raw.split(",") if a.strip()] if author_raw else []
            out.append({
                "title": title,
                "authors": authors,
                "published": published,
                "series": "BOJ Research Paper",
                "abstract": "",
                "pdf_url": pdf_url,
                "url": link,
                "reason": "",
            })
    return out


def _in_window(published: str, now: datetime) -> bool:
    try:
        dt = datetime.fromisoformat(published) if "T" in published else datetime.strptime(published[:10], "%Y-%m-%d")
        return dt >= now - timedelta(days=DETAIL_WINDOW_DAYS)
    except (ValueError, IndexError):
        return True


def _enrich_detail(papers: list[dict]) -> None:
    now = datetime.now()
    targets = []
    for i, p in enumerate(papers):
        if p.get("pdf_url"):
            continue
        recent = _in_window(p.get("published", ""), now) or i < DETAIL_TOP_N
        if recent and p.get("url"):
            targets.append(p)

    if not targets:
        return

    with ThreadPoolExecutor(max_workers=DETAIL_WORKERS) as ex:
        future_map = {ex.submit(_parse_detail_page, p["url"]): p for p in targets}
        for fut in as_completed(future_map):
            p = future_map[fut]
            try:
                detail = fut.result()
            except Exception:
                detail = {"abstract": "", "pdf_url": "", "reason": "抓取失败"}
            _apply_detail(p, detail)

    for p in targets[:DETAIL_TOP_N]:
        if p.get("pdf_url") or p.get("abstract", "").strip():
            continue
        _apply_detail(p, _parse_detail_page(p["url"]))


def _apply_detail(p: dict, detail: dict) -> None:
    if detail.get("pdf_url"):
        p["pdf_url"] = detail["pdf_url"]
    if detail.get("abstract"):
        p["abstract"] = detail["abstract"]
        p["reason"] = ""
    elif not p.get("abstract", "").strip():
        p["reason"] = detail.get("reason") or "抓取失败"
