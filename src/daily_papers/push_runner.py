"""
Full pipeline entry point for daily push (called by cron/launchctl at 7:00 AM).
Runs: fetch → translate → classify → generate HTML → git push → send Feishu
"""

import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

from .filter import get_ai_config, _load_config
from .translator import translate_titles, translate_abstracts
from .monetary import classify_papers
from .push import generate_push_text
from .html_brief import generate_html_brief, generate_pdf, _load_papers
from .docx import generate_docx
from .validator import validate_papers
from .feishu import send_feishu_card
from .crawlers import (
    BISCrawler, NBERCrawler, FedCrawler, ECDCrawler, BOECrawler,
    BOCCrawler, ResHubCrawler, WorldBankCrawler, FDICCrawler,
    BOJCrawler, HKMACrawler, IMFCrawler, SSRNCrawler, MercatusCrawler,
)
from .models import Paper

ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = ROOT / "outputs"


def _git_version() -> str:
    try:
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, timeout=5
        ).stdout.strip()
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5
        ).stdout.strip()
        return f"{branch} {commit}" if branch else commit
    except Exception:
        return "unknown"


def _get_all_crawlers():
    return [
        BISCrawler, NBERCrawler, FedCrawler, ECDCrawler, BOECrawler,
        BOCCrawler, ResHubCrawler, WorldBankCrawler, FDICCrawler,
        BOJCrawler, HKMACrawler, IMFCrawler, SSRNCrawler, MercatusCrawler,
    ]


def _fetch_all() -> list[dict]:
    crawlers = _get_all_crawlers()
    all_papers = []
    for Cls in crawlers:
        c = Cls()
        try:
            papers = c.fetch_papers()
            all_papers.extend(p.to_dict() for p in papers)
            print(f"  [fetch] {c.source_name}: {len(papers)} papers")
        except Exception as e:
            print(f"  [WARN] {c.source_name} fetch failed: {e}")
    return all_papers


def _normalize_missing_reason(papers: list[dict]) -> list[dict]:
    for p in papers:
        if (p.get("abstract") or "").strip():
            p.pop("abstract_missing_reason", None)
        elif not p.get("abstract_missing_reason"):
            p["abstract_missing_reason"] = "无英文摘要"
    return papers


def _filter_recent(papers: list[dict], days: int = 30) -> list[dict]:
    now = datetime.now()
    cutoff = now - timedelta(days=days)
    kept = []
    for p in papers:
        pub = p.get("published", "")
        if not pub:
            kept.append(p)
            continue
        try:
            dt = datetime.fromisoformat(pub) if "T" in pub else datetime.strptime(pub[:10], "%Y-%m-%d")
        except (ValueError, IndexError):
            kept.append(p)
            continue
        if dt >= cutoff:
            kept.append(p)
    return kept


def _load_previous_results() -> list[dict]:
    previous = []
    for d in sorted(OUTPUT_DIR.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        for fname in ("papers.json", "filtered.json"):
            fp = d / fname
            if fp.exists():
                try:
                    previous.extend(json.loads(fp.read_text(encoding="utf-8")))
                except Exception:
                    pass
    return previous


def _merge_cached_results(new_papers: list[dict], previous: list[dict]) -> list[dict]:
    cache = {}
    for p in previous:
        key = p.get("url") or p.get("pdf_url") or p.get("title", "")
        if key:
            cache[key] = p

    results = list(new_papers)
    merged = 0
    for p in results:
        key = p.get("url") or p.get("pdf_url") or p.get("title", "")
        cached = cache.get(key)
        if cached:
            for field in ("title_zh", "is_monetary", "abstract_zh", "abstract_missing_reason"):
                if field in cached and cached[field]:
                    p[field] = cached[field]
                    merged += 1
    if merged:
        print(f"  Merged cached results: {merged} fields")
    return results


def _save_papers(data: list[dict]) -> Path:
    today = datetime.now().strftime("%y%m%d")
    day_dir = OUTPUT_DIR / today
    day_dir.mkdir(parents=True, exist_ok=True)
    path = day_dir / "papers.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return day_dir


def _git_push(brief_path: Path) -> dict:
    try:
        today_dir = brief_path.parent
        today = brief_path.stem

        subprocess.run(["git", "add", "--", str(brief_path), str(brief_path.with_suffix(".pdf")), ], cwd=ROOT, capture_output=True, timeout=30)

        status = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, timeout=15)
        if not status.stdout.strip():
            return {"ok": True, "message": "nothing to commit"}

        subprocess.run(
            ["git", "commit", "-m", f"简报 {today}"],
            cwd=ROOT, capture_output=True, timeout=30,
            env={**__import__("os").environ, "GIT_AUTHOR_NAME": "daily-brief", "GIT_AUTHOR_EMAIL": "daily-brief@local",
                 "GIT_COMMITTER_NAME": "daily-brief", "GIT_COMMITTER_EMAIL": "daily-brief@local"},
        )

        for remote in ("origin", "github"):
            subprocess.run(
                ["git", "push", remote, "master"],
                cwd=ROOT, capture_output=True, text=True, timeout=120,
            )
        return {"ok": True, "message": "pushed"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _push_to_knowledge_base(papers: list[dict]) -> dict:
    """将论文推送到金融多源知识库"""
    kb_root = str(Path(__file__).resolve().parents[5]
                  / "projects" / "金融多源知识库")
    if kb_root not in sys.path:
        sys.path.insert(0, kb_root)
    try:
        from src.db import Database
        from src.vector_store import VectorStore
        from src.ingest import ingest_text
    except ImportError as e:
        return {"ok": False, "pushed": 0, "error": f"import failed: {e}"}

    db = Database()
    vs = VectorStore()
    pushed = 0
    for p in papers:
        title = p.get("title_zh") or p.get("title", "")
        abstract = p.get("abstract_zh") or p.get("abstract", "")
        if not abstract.strip():
            continue
        text = f"# {title}\n\n**作者:** {', '.join(p.get('authors', []))}\n"
        text += f"**来源:** {p.get('source', '')}\n"
        text += f"**日期:** {p.get('published', '')}\n\n{abstract}"
        try:
            ingest_text(
                text=text, title=title, source_type="论文",
                source_url=p.get("url") or p.get("pdf_url", ""),
                author=p.get("source", ""), db=db, vs=vs
            )
            pushed += 1
        except Exception as e:
            print(f"  [KB] ingest failed for '{title}': {e}")
    return {"ok": True, "pushed": pushed}


def run_daily_push() -> dict:
    config = _load_config()
    push_cfg = config.get("push", {})
    test_webhook = push_cfg.get("feishu_webhook_test", "")
    webhook = test_webhook or push_cfg.get("feishu_webhook", "")
    is_test = bool(test_webhook)
    hours = push_cfg.get("time_window_hours", 24)
    gitee_webhook = push_cfg.get("gitee_webhook", "")
    ai_cfg = get_ai_config()
    ai_ready = ai_cfg.get("enabled") and ai_cfg.get("api_key")
    today = datetime.now().strftime("%y%m%d")

    result = {"ok": True, "steps": {}, "total_papers": 0}

    print(f"[{datetime.now().isoformat()}] version: {_git_version()}")

    tag = f"{'【测试】' if is_test else ''}"
    print(f"[{datetime.now().isoformat()}] Fetching papers... {'(TEST MODE)' if is_test else ''}")
    papers = _fetch_all()
    fetch_days = push_cfg.get("fetch_days", 30)
    papers = _filter_recent(papers, days=fetch_days)
    papers = _normalize_missing_reason(papers)
    result["total_papers"] = len(papers)
    print(f"  Fetched {len(papers)} papers (within {fetch_days} days)")

    print("  Merging cached AI results...")
    previous = _load_previous_results()
    papers = _merge_cached_results(papers, previous)
    papers = _normalize_missing_reason(papers)
    fresh = sum(1 for p in papers if not p.get("title_zh"))
    print(f"  {len(papers)} papers, {fresh} need AI processing")

    if ai_ready and papers:
        print("  Translating titles...")
        translated = translate_titles(papers)
        zh_count = sum(1 for p in translated if p.get("title_zh"))
        print(f"  Translated {zh_count}/{len(translated)}")

        print("  Classifying monetary policy relevance...")
        classified = classify_papers(translated)
        mon_count = sum(1 for p in classified if p.get("is_monetary"))
        print(f"  Monetary-related: {mon_count}/{len(classified)}")

        print("  Translating monetary paper abstracts...")
        classified = translate_abstracts(classified, monetary_only=True)
    elif papers:
        classified = papers
    else:
        classified = papers

    day_dir = _save_papers(classified)
    result["steps"]["save"] = str(day_dir / "papers.json")
    print(f"  Saved to {day_dir / 'papers.json'}")

    print("  Validating papers (date filter + AI audit)...")
    passed, filtered = validate_papers(classified, ai_ready=ai_ready)
    day_dir.mkdir(parents=True, exist_ok=True)
    (day_dir / "papers.json").write_text(
        json.dumps(passed, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if filtered:
        (day_dir / "filtered.json").write_text(
            json.dumps(filtered, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    result["steps"]["validation"] = {"passed": len(passed), "filtered": len(filtered)}
    print(f"  Passed: {len(passed)}, Filtered: {len(filtered)}")

    print("  Pushing to knowledge base...")
    kb_result = _push_to_knowledge_base(passed)
    result["steps"]["knowledge_base"] = kb_result
    print(f"  KB: pushed {kb_result.get('pushed', 0)} papers")

    print("  Generating HTML brief...")
    brief_path = generate_html_brief(day_dir, filtered_papers=filtered)
    if brief_path:
        result["steps"]["brief"] = brief_path
        print(f"  HTML brief: {brief_path}")

    print("  Generating PDF...")
    pdf_path = generate_pdf(day_dir)
    if pdf_path:
        result["steps"]["pdf"] = pdf_path
        print(f"  PDF: {pdf_path}")
    else:
        print("  PDF: failed")

    print("  Generating Word docx...")
    docx_path = generate_docx(day_dir)
    if docx_path:
        result["steps"]["docx"] = docx_path
        print(f"  Word: {docx_path}")
    else:
        print("  Word: failed")

    print("  Pushing to Gitee...")
    push_result = _git_push(Path(brief_path) if brief_path else day_dir / "brief.html")
    result["steps"]["git_push"] = push_result
    print(f"  Git push: {push_result.get('ok', False)}")

    print("  Sending Feishu message...")
    if webhook:
        push_text = generate_push_text(day_dir, hours=hours, passed=passed, filtered=filtered)
        card_title = f"📬 货币政策日报{tag}" if is_test else "📬 货币政策日报"
        fr = send_feishu_card(webhook, card_title, push_text)
        result["steps"]["feishu"] = fr.get("ok", False)
        print(f"  Feishu: {fr.get('ok', False)}")
    else:
        result["steps"]["feishu"] = False
        print("  Feishu: skipped (no webhook)")

    print(f"[{datetime.now().isoformat()}] Done.")
    return result


if __name__ == "__main__":
    r = run_daily_push()
    log_path = OUTPUT_DIR / "cron.log"
    with open(log_path, "a") as f:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(json.dumps(r, ensure_ascii=False, indent=2))
