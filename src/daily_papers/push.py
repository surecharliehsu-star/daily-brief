import json
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = ROOT / "outputs"

GITEE_BASE = "https://surecharliehsu-star.github.io/daily-brief"


def _load_papers_from_dir(day_dir: Path) -> list[dict]:
    meta = day_dir / "papers.json"
    if not meta.exists():
        return []
    try:
        return json.loads(meta.read_text(encoding="utf-8"))
    except Exception:
        return []


def _find_date_dirs() -> list[Path]:
    if not OUTPUT_DIR.exists():
        return []
    dirs = sorted([d for d in OUTPUT_DIR.iterdir() if d.is_dir()], reverse=True)
    return [d for d in dirs if (d / "papers.json").exists()]


def _is_within_window(pub: str, now: datetime, hours: int) -> bool:
    if not pub:
        return False
    try:
        if "T" in pub:
            dt = datetime.fromisoformat(pub)
        else:
            dt = datetime.strptime(pub, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
    except ValueError:
        return False
    cutoff = now - timedelta(hours=hours)
    return dt >= cutoff


def generate_push_text(day_dir: Path | None = None, hours: int = 24,
                       passed: list[dict] | None = None,
                       filtered: list[dict] | None = None) -> str:
    now = datetime.now()

    if passed is not None and filtered is not None:
        all_papers = passed + filtered
        papers = passed
    else:
        dirs = _find_date_dirs()
        if not dirs:
            return "暂无数据"
        papers = _load_papers_from_dir(dirs[0])
        all_papers = papers
        fp = dirs[0] / "filtered.json"
        if fp.exists():
            all_papers += json.loads(fp.read_text(encoding="utf-8"))

    dates = []
    for p in all_papers:
        pub = p.get("published", "")
        if pub:
            try:
                dt = datetime.fromisoformat(pub) if "T" in pub else datetime.strptime(pub[:10], "%Y-%m-%d")
                dates.append(dt)
            except (ValueError, IndexError):
                pass
    cover = ""
    if dates:
        cover = f"📅 覆盖: {min(dates).strftime('%Y-%m-%d')} ~ {max(dates).strftime('%Y-%m-%d')}"

    monetary_today = [p for p in papers if p.get("is_monetary") and _is_within_window(p.get("published", ""), now, hours)]
    monetary_today.sort(key=lambda x: x.get("published", ""), reverse=True)

    total_7d = len(papers)
    mon_7d = sum(1 for p in papers if p.get("is_monetary"))
    total_30d = len(all_papers)
    mon_30d = sum(1 for p in all_papers if p.get("is_monetary"))
    srcc = len(set(p.get("source", "") for p in all_papers))
    brief_url = f"{GITEE_BASE}/outputs/{now.strftime('%y%m%d')}/brief.pdf"

    lines = [f"📬 货币政策日报 — {now.strftime('%Y-%m-%d')}", ""]
    if cover:
        lines.append(cover)
        lines.append("")

    lines.append(f"📄 [查看完整简报]({brief_url}) | 近7天: {total_7d}篇(货币{mon_7d}篇) · 近30天: {total_30d}篇(货币{mon_30d}篇) · {srcc}个源")
    lines.append("")

    lines.append("📋 今日更新：")
    lines.append("")

    for i, p in enumerate(monetary_today, 1):
        pub = p.get("published", "")[:10] if p.get("published") else "??"
        src = p.get("source", "")
        title_zh = p.get("title_zh", "") or ""
        title_en = p.get("title", "")
        url = p.get("url", "") or p.get("pdf_url", "")
        authors = p.get("authors", [])
        author_str = ", ".join(authors[:3]) if authors else ""
        if len(authors) > 3:
            author_str += " et al."

        if url:
            lines.append(f"{i}. [{title_zh}]({url})")
        else:
            lines.append(f"{i}. {title_zh}")
        lines.append(f"   {title_en}")
        lines.append(f"   📅 {pub} · {src}" + (f" · {author_str}" if author_str else ""))
        lines.append("")

    if not monetary_today:
        lines.append("（无）")
        lines.append("")

    return "\n".join(lines)
