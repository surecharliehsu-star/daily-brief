import html
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = ROOT / "outputs"

SOURCE_EMOJI = {
    "BIS": "🏦", "NBER": "📊", "Federal Reserve Board": "🇺🇸",
    "ECB": "🏛️", "Bank of England": "🇬🇧", "Bank of Canada": "🍁",
    "BIS Research Hub": "🌐", "World Bank": "🌍", "FDIC": "🏛️",
    "Bank of Japan": "🗾", "HKMA": "🇭🇰", "IMF": "🌏",
    "SSRN": "📚", "Mercatus": "🏫",
}

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>每日简报 - {date}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:#f5f5f7;color:#1d1d1f;line-height:1.6}}
.container{{max-width:800px;margin:0 auto;padding:16px}}
.header{{background:linear-gradient(135deg,#1a1a2e,#16213e);color:#fff;padding:32px 24px;border-radius:16px;margin-bottom:24px}}
.header h1{{font-size:24px;margin-bottom:8px}}
.header .meta{{opacity:.8;font-size:14px}}
.section{{background:#fff;border-radius:12px;padding:20px;margin-bottom:16px;box-shadow:0 1px 3px rgba(0,0,0,.08)}}
.section h2{{font-size:18px;margin-bottom:16px;padding-bottom:8px;border-bottom:2px solid #f0f0f0}}
.section.monetary h2{{border-bottom-color:#ff4d4f;color:#cf1322}}
.section.filtered{{background:#fafafa;border:1px solid #e8e8e8;opacity:.7}}
.section.filtered h2{{border-bottom-color:#ccc;color:#999;font-size:15px}}
.paper{{padding:12px 0;border-bottom:1px solid #f0f0f0}}
.paper:last-child{{border-bottom:none;padding-bottom:0}}
.paper.monetary{{background:#fff2f0;margin:0 -12px;padding:12px;border-radius:8px;border-bottom:1px solid #ffd8bf}}
.paper.monetary:last-child{{border-bottom:none;margin-bottom:0}}
.paper .meta{{font-size:12px;color:#888;margin-bottom:4px}}
.paper .title-zh{{font-size:16px;font-weight:600;margin-bottom:2px}}
.paper .title-en{{font-size:14px;color:#555;margin-bottom:4px}}
.paper .authors{{font-size:13px;color:#777}}
.paper .abstract{{font-size:13px;color:#444;margin-top:6px;padding:8px;background:#f9f9fb;border-left:3px solid #2563eb;border-radius:4px;line-height:1.5}}
.paper .abstract-missing{{font-size:13px;color:#999;font-style:italic;margin-top:6px;padding:8px;background:#fafafa;border-left:3px solid #ddd;border-radius:4px;line-height:1.5}}
.tag{{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;margin-right:6px}}
.tag-mon{{background:#ff4d4f;color:#fff}}
.tag-src{{background:#e8e8e8;color:#555}}
.tag-est{{display:inline-block;font-size:10px;color:#999;background:#f0f0f0;padding:1px 5px;border-radius:3px;margin-left:2px}}
a{{color:#2563eb;text-decoration:none}}
a:hover{{text-decoration:underline}}
.footer{{text-align:center;color:#999;font-size:12px;padding:24px 0}}
</style>
</head>
<body>
<div class="container">
<div class="header">
<h1>📬 每日简报</h1>
<div class="meta">{date} · 7天内{total}篇(货币{mon_count}篇) · 30天内{ftotal}篇(货币{fmon}篇) · {sources}个来源</div>
</div>
{monetary_section}
{others_section}
{filtered_section}
<div class="footer">自动生成 · {gen_time}</div>
</div>
</body>
</html>"""


def _load_papers(day_dir: Path) -> list[dict]:
    path = day_dir / "papers.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _format_paper_html(p: dict, is_monetary: bool) -> str:
    pub = p.get("published", "")[:10] if p.get("published") else "??"
    src = p.get("source", "")
    emoji = SOURCE_EMOJI.get(src, "📄")
    title_zh = html.escape(p.get("title_zh", "") or "")
    title_en = html.escape(p.get("title", ""))
    authors = p.get("authors", [])
    author_str = ", ".join(authors[:3]) if authors else ""
    if len(authors) > 3:
        author_str += " et al."

    cls = 'paper monetary' if is_monetary else 'paper'
    tag = '<span class="tag tag-mon">🔴 货币政策</span>' if is_monetary else ''
    src_tag = f'<span class="tag tag-src">{emoji} {html.escape(src)}</span>'

    url = html.escape(p.get("url", "") or "")
    estimated = ' <span class="tag-est">推定</span>' if p.get("date_estimated") else ""
    lines = [f'<div class="{cls}">']
    lines.append(f'<div class="meta">{pub}{estimated} · {src_tag} {tag}</div>')
    if title_zh:
        title = f'<a href="{url}" target="_blank" rel="noopener">{title_zh}</a>' if url else title_zh
        lines.append(f'<div class="title-zh">{title}</div>')
    title = f'<a href="{url}" target="_blank" rel="noopener">{title_en}</a>' if url else title_en
    lines.append(f'<div class="title-en">{title}</div>')
    if author_str:
        lines.append(f'<div class="authors">{html.escape(author_str)}</div>')
    if is_monetary:
        abstract_zh = p.get("abstract_zh", "") or ""
        if abstract_zh:
            lines.append(f'<div class="abstract">{html.escape(abstract_zh)}</div>')
        else:
            lines.append('<div class="abstract-missing">（摘要暂缺，次日自动补齐）</div>')
    lines.append("</div>")
    return "\n".join(lines)


def generate_html_brief(day_dir: Path | None = None, filtered_papers: list[dict] | None = None) -> str:
    if day_dir is None:
        dirs = sorted([d for d in OUTPUT_DIR.iterdir() if d.is_dir()], reverse=True)
        day_dir = dirs[0] if dirs else None
    if day_dir is None:
        return ""

    papers = _load_papers(day_dir)
    papers.sort(key=lambda x: x.get("published", ""), reverse=True)

    monetary = [p for p in papers if p.get("is_monetary")]
    others = [p for p in papers if not p.get("is_monetary")]

    mon_html = "\n".join(_format_paper_html(p, True) for p in monetary)
    others_html = "\n".join(_format_paper_html(p, False) for p in others)

    mon_section = f'<div class="section monetary"><h2>🔴 7天内货币政策相关（{len(monetary)}篇）</h2>{mon_html}</div>' if monetary else ""
    others_section = f'<div class="section"><h2>📋 7天内论文非货币政策相关（{len(others)}篇）</h2>{others_html}</div>' if others else ""

    filtered_section = ""
    if filtered_papers:
        filtered_mon = sorted([p for p in filtered_papers if p.get("is_monetary")], key=lambda x: x.get("published", ""), reverse=True)
        filtered_other = sorted([p for p in filtered_papers if not p.get("is_monetary")], key=lambda x: x.get("published", ""), reverse=True)
        f_html = "\n".join(_format_paper_html(p, p.get("is_monetary", False)) for p in filtered_mon + filtered_other)
        filtered_section = f'<div class="section filtered"><h2>⛔ 30天内论文（货币政策{len(filtered_mon)}篇；非货币政策{len(filtered_other)}篇）</h2>{f_html}</div>'

    date_obj = datetime.now()
    date_str = date_obj.strftime("%Y-%m-%d")
    gen_str = date_obj.strftime("%Y-%m-%d %H:%M")

    src_count = len(set(p.get("source", "") for p in papers))
    fmon = len(filtered_mon) if filtered_papers else 0
    fother = len(filtered_other) if filtered_papers else 0
    ftotal = fmon + fother

    html_content = HTML_TEMPLATE.format(
        date=date_str,
        total=len(papers),
        sources=src_count,
        mon_count=len(monetary),
        ftotal=ftotal,
        fmon=fmon,
        fother=fother,
        monetary_section=mon_section,
        others_section=others_section,
        filtered_section=filtered_section,
        gen_time=gen_str,
    )

    brief_path = day_dir / "brief.html"
    brief_path.write_text(html_content, encoding="utf-8")
    return str(brief_path)


def generate_pdf(day_dir: Path) -> str | None:
    html_path = day_dir / "brief.html"
    if not html_path.exists():
        return None
    pdf_path = day_dir / "brief.pdf"
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(f"file://{html_path.resolve()}")
            page.pdf(path=str(pdf_path), format="A4", margin={"top": "15mm", "bottom": "15mm", "left": "12mm", "right": "12mm"})
            browser.close()
        return str(pdf_path)
    except Exception:
        return None
