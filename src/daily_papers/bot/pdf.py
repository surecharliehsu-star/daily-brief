"""原文 PDF 下载与文本提取。失败时返回 None 以便降级为摘要翻译。"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
}


def _pdf_url(paper: dict) -> str:
    return (paper.get("pdf_url") or "").strip()


def _download(url: str, dest: Path) -> bool:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30, allow_redirects=True)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
        return True
    except Exception as e:
        print(f"[PDF] download failed {url}: {e}", flush=True)
        return False


def _extract_text(pdf_path: Path) -> str | None:
    try:
        import fitz
    except ImportError:
        return None
    try:
        doc = fitz.open(pdf_path)
        pages = []
        for page in doc:
            pages.append(page.get_text("text"))
        doc.close()
        return "\n\n".join(pages)
    except Exception as e:
        print(f"[PDF] extract failed: {e}", flush=True)
        return None


def _clean_text(text: str) -> str:
    if not text:
        return ""
    # 移除孤立的换行（英文句子在跨行处拼接），保留段落空行
    lines = text.split("\n")
    out = []
    for i, line in enumerate(lines):
        s = line.strip()
        if not s:
            out.append("")
            continue
        prev = out[-1] if out else ""
        if prev and not re.search(r"[.?!\:;,\)\}\"\']$", prev) and re.match(r"^[a-z0-9(\[\"]", s):
            out[-1] = prev + " " + s
        else:
            out.append(s)
    block = "\n".join(out)
    block = re.sub(r"[ \t]+", " ", block)
    block = re.sub(r"\n{3,}", "\n\n", block)
    return block.strip()


def fetch_and_extract(paper: dict, cache_dir: Path | None = None) -> tuple[str | None, str]:
    """下载 PDF 并提取文本。返回 (text, source)。
    source 描述内容来源：'pdf:<文件名>' / 'abstract:<来源>'
    """
    url = _pdf_url(paper)
    abstract = (paper.get("abstract") or "").strip()
    if not url:
        if abstract:
            return abstract, f"abstract:{paper.get('source', '')}"
        return None, "paper has no pdf_url and no abstract"

    ext = url.split("#")[0].split("?")[0].rsplit(".", 1)[-1].lower() if "." in url.split("?")[0] else "pdf"
    if ext != "pdf":
        ext = "pdf"

    cache_dir = cache_dir or None
    key = hashlib.md5(url.encode()).hexdigest()[:12]
    if cache_dir is None:
        root = Path(__file__).resolve().parents[3]
        cache_dir = root / "outputs" / "fulltext_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = cache_dir / f"{key}.pdf"

    if not pdf_path.exists():
        if not _download(url, pdf_path):
            if abstract:
                return abstract, f"abstract:download_failed"
            return None, "download failed and no abstract"
    else:
        # 空文件重下
        if pdf_path.stat().st_size < 100:
            if not _download(url, pdf_path):
                if abstract:
                    return abstract, "abstract:download_failed"
                return None, "download failed and no abstract"

    text = _extract_text(pdf_path)
    if text is None or not text.strip():
        if abstract:
            return abstract, f"abstract:extract_failed"
        return None, "extract failed and no abstract"

    return _clean_text(text), f"pdf:{pdf_path.name}"