from datetime import datetime


_SOURCE_EMOJI = {
    "BIS": "🏦",
    "NBER": "📊",
    "Federal Reserve Board": "🇺🇸",
    "ECB": "🏛️",
    "Bank of England": "🇬🇧",
    "Bank of Canada": "🍁",
    "BIS Research Hub": "🌐",
    "World Bank": "🌍",
    "FDIC": "🏛️",
    "Bank of Japan": "🗾",
    "HKMA": "🇭🇰",
    "IMF": "🌏",
    "SSRN": "📚",
    "Mercatus": "🏫",
}

_SOURCE_ORDER = [
    "BIS", "NBER", "Federal Reserve Board", "ECB", "Bank of England",
    "Bank of Canada", "BIS Research Hub", "World Bank", "FDIC",
    "Bank of Japan", "HKMA", "IMF", "SSRN", "Mercatus",
]


def _source_emoji(source: str) -> str:
    return _SOURCE_EMOJI.get(source, "📄")


def generate_report(papers: list[dict]) -> str:
    source_order = _SOURCE_ORDER
    grouped = {}
    for p in papers:
        grouped.setdefault(p.get("source", "Unknown"), []).append(p)

    lines: list[str] = []
    date_str = datetime.now().strftime("%Y-%m-%d")
    lines.append(f"# 每日论文简报 — {date_str}")
    lines.append("")

    total = len(papers)
    matched = sum(1 for p in papers if p.get("_matched", False))
    scored = sum(1 for p in papers if p.get("_ai_score", 0) > 0)
    high_priority = sum(1 for p in papers if p.get("_ai_score", 0) >= 4)
    ai_enabled = any(p.get("_ai_score", 0) > 0 for p in papers)

    parts = [f"共 {total} 篇论文 | 关键词命中 {matched} 篇"]
    if ai_enabled:
        parts.append(f"AI 评分 {scored} 篇 | 重点关注 {high_priority} 篇")
    lines.append(f"> {' | '.join(parts)}")
    lines.append("")

    for src in source_order:
        if src not in grouped:
            continue
        src_papers = grouped[src]
        emoji = _source_emoji(src)
        lines.append(f"## {emoji} {src}")
        lines.append("")

        matched_src = [p for p in src_papers if p.get("_matched", False)]
        unmatched_src = [p for p in src_papers if not p.get("_matched", False)]

        if ai_enabled:
            focused = [p for p in matched_src if p.get("_ai_score", 0) >= 4]
            overview = [p for p in matched_src if p.get("_ai_score", 0) == 3]
            archived = [p for p in matched_src if 1 <= p.get("_ai_score", 0) <= 2]
            no_score = [p for p in matched_src if p.get("_ai_score", 0) == 0]
        else:
            focused = []
            overview = []
            archived = []
            no_score = sorted(matched_src, key=lambda p: p.get("_keyword_count", 0), reverse=True)

        if focused:
            lines.append("### ⭐ 重点关注")
            lines.append("")
            for p in sorted(focused, key=lambda x: -x.get("_ai_score", 0)):
                _write_detail(lines, p)
                lines.append("")

        if overview:
            lines.append("### 📌 速览")
            lines.append("")
            for p in sorted(overview, key=lambda x: -x.get("_ai_score", 0)):
                _write_summary(lines, p)
            lines.append("")

        if archived:
            lines.append("### 📁 归档")
            lines.append("")
            for p in sorted(archived, key=lambda x: -x.get("_ai_score", 0)):
                _write_compact(lines, p)
            lines.append("")

        if no_score:
            lines.append("### ⏳ 待评分")
            lines.append("")
            for p in sorted(no_score, key=lambda x: -x.get("_keyword_count", 0)):
                _write_pending(lines, p)
            lines.append("")

        if unmatched_src:
            lines.append("### 其他")
            lines.append("")
            for p in unmatched_src:
                lines.append(f"- {p.get('title', '')}")
            lines.append("")

    lines.append("---")
    lines.append(f"_共计 {total} 篇，来自 {len([g for g in grouped if grouped[g]])} 个来源_")
    lines.append("")

    return "\n".join(lines)


def _write_detail(lines: list[str], p: dict):
    title = p.get("title", "")
    authors = ", ".join(p.get("authors", []))
    published = p.get("published", "") or "N/A"
    url = p.get("url", "")
    pdf_url = p.get("pdf_url", "")
    score = p.get("_ai_score", 0)
    reason = p.get("_ai_reason", "")
    kw = ", ".join(p.get("_keywords_hit", []))
    abstract = p.get("abstract", "")

    lines.append(f"**{title}**")
    lines.append(f"- 作者：{authors} | 日期：{published}")
    if kw:
        lines.append(f"- 关键词匹配：{kw}")
    lines.append(f"- AI 评分：{score}/5 — {reason}")
    if abstract:
        lines.append(f"- 摘要：{abstract[:300]}...")
    lines.append(f"- 链接：[论文页]({url}) | [PDF]({pdf_url})")


def _write_summary(lines: list[str], p: dict):
    title = p.get("title", "")
    score = p.get("_ai_score", 0)
    reason = p.get("_ai_reason", "")
    kw = ", ".join(p.get("_keywords_hit", []))
    url = p.get("url", "")
    line = f"- **[{title}]({url})** — 评分 {score}/5"
    if kw:
        line += f" | 关键词：{kw}"
    if reason:
        line += f" | {reason}"
    lines.append(line)


def _write_compact(lines: list[str], p: dict):
    title = p.get("title", "")
    score = p.get("_ai_score", 0)
    kw = ", ".join(p.get("_keywords_hit", []))
    reason = p.get("_ai_reason", "")
    line = f"- {title} — 评分 {score}/5"
    if kw:
        line += f" | 关键词：{kw}"
    if reason:
        line += f" | {reason}"
    lines.append(line)


def _write_pending(lines: list[str], p: dict):
    title = p.get("title", "")
    kw = ", ".join(p.get("_keywords_hit", []))
    abstract = p.get("abstract", "")
    url = p.get("url", "")
    pdf_url = p.get("pdf_url", "")
    lines.append(f"- **{title}**")
    if kw:
        lines.append(f"  - 匹配关键词：{kw}")
    if abstract:
        lines.append(f"  - 摘要：{abstract[:200]}...")
    lines.append(f"  - 链接：[论文页]({url}) | [PDF]({pdf_url})")
