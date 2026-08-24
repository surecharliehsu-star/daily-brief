import json
from pathlib import Path
from datetime import datetime

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool, Resource

from .crawlers import (
    BISCrawler, NBERCrawler, FedCrawler, ECDCrawler, BOECrawler,
    BOCCrawler, ResHubCrawler, WorldBankCrawler, FDICCrawler,
    BOJCrawler, HKMACrawler, IMFCrawler, SSRNCrawler, MercatusCrawler,
)
from .models import Paper
from .filter import KeywordFilter, get_keywords, set_keywords, get_ai_config, set_ai_config
from .scorer import score_papers
from .report import generate_report
from .translator import translate_titles
from .monetary import classify_papers
from .push_runner import run_daily_push

ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = ROOT / "outputs"

server = Server("daily-papers")


def _save_papers(date_str: str, papers: list[Paper]):
    day_dir = OUTPUT_DIR / date_str
    day_dir.mkdir(parents=True, exist_ok=True)
    meta = day_dir / "papers.json"
    existing = []
    if meta.exists():
        existing = json.loads(meta.read_text(encoding="utf-8"))
    seen = {p["url"] for p in existing}
    new = [p.to_dict() for p in papers if p.url not in seen]
    existing.extend(new)
    meta.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(new)


def _latest_output_dir():
    if not OUTPUT_DIR.exists():
        return None
    dirs = sorted([d for d in OUTPUT_DIR.iterdir() if d.is_dir()], reverse=True)
    for d in dirs:
        if (d / "papers.json").exists():
            return d
    return None


def _read_papers(dir_path):
    meta = dir_path / "papers.json"
    if not meta.exists():
        return []
    try:
        return json.loads(meta.read_text(encoding="utf-8"))
    except Exception:
        return []


@server.list_resources()
async def list_resources() -> list[Resource]:
    return [
        Resource(
            uri="daily-papers://papers/latest",
            name="Latest Papers",
            description="Most recent crawl results from all sources",
            mimeType="application/json",
        ),
        Resource(
            uri="daily-papers://stats",
            name="System Statistics",
            description="Total papers collected, last run date, per-source counts",
            mimeType="application/json",
        ),
    ]


@server.read_resource()
async def read_resource(uri: str) -> str:
    if uri == "daily-papers://papers/latest":
        d = _latest_output_dir()
        if not d:
            return json.dumps({"date": "", "papers": [], "message": "No data yet"}, ensure_ascii=False, indent=2)
        papers = _read_papers(d)
        return json.dumps({"date": d.name, "papers": papers, "count": len(papers)}, ensure_ascii=False, indent=2)

    if uri == "daily-papers://stats":
        stats = {"total_papers": 0, "last_run": None, "sources": {}}
        if OUTPUT_DIR.exists():
            dirs = sorted([d for d in OUTPUT_DIR.iterdir() if d.is_dir()], reverse=True)
            for d in dirs:
                papers = _read_papers(d)
                for p in papers:
                    stats["total_papers"] += 1
                    src = p.get("source", "Unknown")
                    stats["sources"][src] = stats["sources"].get(src, 0) + 1
            if dirs:
                stats["last_run"] = dirs[0].name
        return json.dumps(stats, ensure_ascii=False, indent=2)

    raise ValueError(f"Unknown resource: {uri}")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="fetch_bis_papers",
            description="Fetch latest working papers from BIS",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "number", "description": "Max papers to return", "default": 10}
                },
            },
        ),
        Tool(
            name="fetch_nber_papers",
            description="Fetch latest working papers from NBER",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "number", "description": "Max papers to return", "default": 10}
                },
            },
        ),
        Tool(
            name="fetch_fed_papers",
            description="Fetch latest FEDS working papers from the Federal Reserve Board",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "number", "description": "Max papers to return", "default": 10}
                },
            },
        ),
        Tool(
            name="fetch_ecb_papers",
            description="Fetch latest working papers from the European Central Bank",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "number", "description": "Max papers to return", "default": 10}
                },
            },
        ),
        Tool(
            name="fetch_boe_papers",
            description="Fetch latest working papers from the Bank of England",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "number", "description": "Max papers to return", "default": 10}
                },
            },
        ),
        Tool(
            name="fetch_boc_papers",
            description="Fetch latest working papers from the Bank of Canada",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "number", "description": "Max papers to return", "default": 10}
                },
            },
        ),
        Tool(
            name="fetch_reshub_papers",
            description="Fetch latest papers from BIS Central Bank Research Hub (aggregated from central banks worldwide)",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "number", "description": "Max papers to return", "default": 10}
                },
            },
        ),
        Tool(
            name="fetch_worldbank_papers",
            description="Fetch latest working papers from the World Bank",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "number", "description": "Max papers to return", "default": 10}
                },
            },
        ),
        Tool(
            name="fetch_fdic_papers",
            description="Fetch latest publications from FDIC",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "number", "description": "Max papers to return", "default": 10}
                },
            },
        ),
        Tool(
            name="fetch_boj_papers",
            description="Fetch latest research papers from the Bank of Japan",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "number", "description": "Max papers to return", "default": 10}
                },
            },
        ),
        Tool(
            name="fetch_hkma_papers",
            description="Fetch latest research papers from the Hong Kong Monetary Authority",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "number", "description": "Max papers to return", "default": 10}
                },
            },
        ),
        Tool(
            name="fetch_imf_papers",
            description="Fetch latest working papers from the IMF",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "number", "description": "Max papers to return", "default": 10}
                },
            },
        ),
        Tool(
            name="fetch_ssrn_papers",
            description="Fetch latest papers from SSRN (requires WebFetch browser)",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "number", "description": "Max papers to return", "default": 10}
                },
            },
        ),
        Tool(
            name="fetch_mercatus_papers",
            description="Fetch latest working papers from the Mercatus Center",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "number", "description": "Max papers to return", "default": 10}
                },
            },
        ),
        Tool(
            name="fetch_all_papers",
            description="Fetch latest papers from all 14 supported sources and save to storage",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "number", "description": "Max papers per source", "default": 10}
                },
            },
        ),
        Tool(
            name="search_papers",
            description="Search previously fetched papers by keyword in title or abstract",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search keyword"},
                    "max_results": {"type": "number", "description": "Max results (default 20)"},
                    "source": {"type": "string", "description": "Filter by source name (BIS, NBER, Federal Reserve Board, ECB, Bank of England, Bank of Canada, BIS Research Hub, World Bank, FDIC, Bank of Japan, HKMA, IMF, SSRN, Mercatus)"},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="filter_papers",
            description="Apply keyword matching and optional AI scoring to stored papers. Configurable keywords in config.json.",
            inputSchema={
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "Filter by source name (BIS, NBER, Federal Reserve Board, ECB, Bank of England, Bank of Canada, BIS Research Hub, World Bank, FDIC, Bank of Japan, HKMA, IMF, SSRN, Mercatus)"},
                    "limit": {"type": "number", "description": "Max results per source (default 30)"},
                },
            },
        ),
        Tool(
            name="generate_report",
            description="Generate a daily markdown brief from filtered papers",
            inputSchema={
                "type": "object",
                "properties": {
                    "include_archived": {"type": "boolean", "description": "Include low-score papers in archive section (default true)"},
                },
            },
        ),
        Tool(
            name="configure",
            description="Update keywords or DeepSeek AI scoring settings",
            inputSchema={
                "type": "object",
                "properties": {
                    "keywords_en": {"type": "array", "items": {"type": "string"}, "description": "English keywords"},
                    "keywords_zh": {"type": "array", "items": {"type": "string"}, "description": "Chinese keywords"},
                    "deepseek_api_key": {"type": "string", "description": "DeepSeek API key (leave empty to disable AI scoring)"},
                    "deepseek_model": {"type": "string", "description": "Model name (default deepseek-chat)"},
                },
            },
        ),
        Tool(
            name="daily_push",
            description="Run daily push pipeline: fetch recent papers, translate, classify, generate push.md, send to Feishu",
            inputSchema={
                "type": "object",
                "properties": {
                    "hours": {"type": "number", "description": "Time window in hours (default 24)"},
                },
            },
        ),
        Tool(
            name="translate_papers",
            description="Translate English paper titles to Chinese using DeepSeek",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="classify_papers",
            description="Classify papers as monetary-policy-related or not using DeepSeek",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="setup_feishu",
            description="Set Feishu group webhook URL for daily push",
            inputSchema={
                "type": "object",
                "properties": {
                    "webhook_url": {"type": "string", "description": "Feishu group robot webhook URL"},
                },
                "required": ["webhook_url"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    limit = int(arguments.get("limit", 10))

    _crawler_map = {
        "fetch_bis_papers": BISCrawler,
        "fetch_nber_papers": NBERCrawler,
        "fetch_fed_papers": FedCrawler,
        "fetch_ecb_papers": ECDCrawler,
        "fetch_boe_papers": BOECrawler,
        "fetch_boc_papers": BOCCrawler,
        "fetch_reshub_papers": ResHubCrawler,
        "fetch_worldbank_papers": WorldBankCrawler,
        "fetch_fdic_papers": FDICCrawler,
        "fetch_boj_papers": BOJCrawler,
        "fetch_hkma_papers": HKMACrawler,
        "fetch_imf_papers": IMFCrawler,
        "fetch_ssrn_papers": SSRNCrawler,
        "fetch_mercatus_papers": MercatusCrawler,
    }

    if name in _crawler_map:
        crawler = _crawler_map[name]()
        papers = crawler.fetch_papers(limit=limit)
        today = datetime.now().strftime("%y%m%d")
        new = _save_papers(today, papers)
        return [TextContent(
            type="text",
            text=json.dumps({
                "source": crawler.source_name,
                "count": len(papers),
                "new_saved": new,
                "papers": [p.to_dict() for p in papers],
            }, ensure_ascii=False, indent=2),
        )]

    if name == "fetch_all_papers":
        limit = arguments.get("limit")
        if limit is not None:
            limit = int(limit)
        all_papers: list[Paper] = []
        results = {}
        from concurrent.futures import ThreadPoolExecutor, as_completed

        all_crawlers = [
            BISCrawler, NBERCrawler, FedCrawler, ECDCrawler, BOECrawler,
            BOCCrawler, ResHubCrawler, WorldBankCrawler, FDICCrawler,
            BOJCrawler, HKMACrawler, IMFCrawler, SSRNCrawler, MercatusCrawler,
        ]

        def _run(crawler_cls):
            c = crawler_cls()
            try:
                ps = c.fetch_papers(limit=limit)
                return c.source_name, ps
            except Exception as e:
                return c.source_name, f"error: {e}"

        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(_run, cls) for cls in all_crawlers]
            for fut in as_completed(futures):
                src, ps = fut.result()
                if isinstance(ps, list):
                    all_papers.extend(ps)
                    results[src] = len(ps)
                else:
                    results[src] = ps
        today = datetime.now().strftime("%y%m%d")
        new = _save_papers(today, all_papers)
        return [TextContent(
            type="text",
            text=json.dumps({
                "sources": results,
                "total": len(all_papers),
                "new_saved": new,
                "papers": [p.to_dict() for p in all_papers],
            }, ensure_ascii=False, indent=2),
        )]

    if name == "search_papers":
        query = arguments.get("query", "").lower()
        max_results = int(arguments.get("max_results", 20))
        source_filter = (arguments.get("source") or "").lower()
        d = _latest_output_dir()
        if not d:
            return [TextContent(type="text", text=json.dumps({"error": "No data yet"}, ensure_ascii=False))]
        papers = _read_papers(d)
        results = []
        for p in papers:
            if source_filter and source_filter not in p.get("source", "").lower():
                continue
            title = p.get("title") or ""
            abstract = p.get("abstract") or ""
            topics = " ".join(p.get("topics") or [])
            text = (title + " " + abstract + " " + topics).lower()
            if query not in text:
                continue
            results.append({
                "title": p.get("title", ""),
                "url": p.get("url", ""),
                "source": p.get("source", ""),
                "published": p.get("published", ""),
                "abstract": (p.get("abstract") or "")[:300],
            })
            if len(results) >= max_results:
                break
        return [TextContent(
            type="text",
            text=json.dumps({"total": len(results), "results": results}, ensure_ascii=False, indent=2),
        )]

    if name == "filter_papers":
        source_filter = (arguments.get("source") or "").lower()
        filter_limit = int(arguments.get("limit", 30))
        d = _latest_output_dir()
        if not d:
            return [TextContent(type="text", text=json.dumps({"error": "No data yet"}, ensure_ascii=False))]
        papers = _read_papers(d)

        if source_filter:
            papers = [p for p in papers if source_filter in p.get("source", "").lower()]

        kf = KeywordFilter()
        filtered = kf.filter(papers)

        relevant = [p for p in filtered if p["_matched"]]

        ai_config = get_ai_config()
        if ai_config.get("enabled") and ai_config.get("api_key"):
            scored = await score_papers(relevant)
        else:
            scored = [{**p, "_ai_score": 0, "_ai_reason": "AI scoring not configured (use `configure` to set API key)"} for p in relevant]

        total = len(papers)
        matched = len(relevant)
        scored_count = sum(1 for s in scored if s.get("_ai_score", 0) > 0)

        results_data = []
        for s in sorted(scored, key=lambda x: -x.get("_ai_score", 0)):
            results_data.append({
                "title": s["title"],
                "url": s["url"],
                "source": s["source"],
                "published": s.get("published", ""),
                "authors": s.get("authors", []),
                "keywords_hit": s["_keywords_hit"],
                "ai_score": s.get("_ai_score", 0),
                "ai_reason": s.get("_ai_reason", ""),
                "abstract": (s.get("abstract") or "")[:300],
            })

        return [TextContent(
            type="text",
            text=json.dumps({
                "total_papers": total,
                "keyword_matched": matched,
                "ai_scored": scored_count,
                "results": results_data,
            }, ensure_ascii=False, indent=2),
        )]

    if name == "generate_report":
        d = _latest_output_dir()
        if not d:
            return [TextContent(type="text", text=json.dumps({"error": "No data yet"}, ensure_ascii=False))]
        papers = _read_papers(d)

        kf = KeywordFilter()
        filtered = kf.filter(papers)

        ai_config = get_ai_config()
        if ai_config.get("enabled") and ai_config.get("api_key"):
            matched = [p for p in filtered if p["_matched"]]
            scored_matched = await score_papers(matched)
            scored_all = [{**p, "_ai_score": 0, "_ai_reason": "not scored"} for p in filtered if not p["_matched"]]
            scored_all.extend(scored_matched)
        else:
            scored_all = [{**p, "_ai_score": 0, "_ai_reason": "AI scoring not configured"} for p in filtered]

        report = generate_report(scored_all)

        report_path = d / "report.md"
        report_path.write_text(report, encoding="utf-8")

        return [TextContent(
            type="text",
            text=json.dumps({
                "report_path": str(report_path),
                "report": report,
            }, ensure_ascii=False, indent=2),
        )]

    if name == "configure":
        changes = []
        if "keywords_en" in arguments:
            current = get_keywords()
            set_keywords(en=arguments["keywords_en"])
            changes.append(f"English keywords updated ({len(arguments['keywords_en'])} items)")
        if "keywords_zh" in arguments:
            set_keywords(zh=arguments["keywords_zh"])
            changes.append(f"Chinese keywords updated ({len(arguments['keywords_zh'])} items)")
        if "deepseek_api_key" in arguments:
            key = arguments["deepseek_api_key"]
            set_ai_config(enabled=bool(key), api_key=key)
            changes.append(f"DeepSeek API key {'set' if key else 'cleared'}")
        if "deepseek_model" in arguments:
            set_ai_config(model=arguments["deepseek_model"])
            changes.append(f"Model set to {arguments['deepseek_model']}")

        cfg = {"keywords": get_keywords(), "ai_scoring": get_ai_config()}
        return [TextContent(
            type="text",
            text=json.dumps({"changes": changes, "config": cfg}, ensure_ascii=False, indent=2),
        )]

    if name == "daily_push":
        hours = int(arguments.get("hours", 24))
        result = run_daily_push()
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

    if name == "translate_papers":
        d = _latest_output_dir()
        if not d:
            return [TextContent(type="text", text=json.dumps({"error": "No data yet"}))]
        papers = _read_papers(d)
        translated = translate_titles(papers)
        d / "papers.json"
        Path(d / "papers.json").write_text(
            json.dumps(translated, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        translated_count = sum(1 for p in translated if p.get("title_zh"))
        return [TextContent(type="text", text=json.dumps({
            "total": len(translated),
            "translated": translated_count,
            "sample": translated[0] if translated else None,
        }, ensure_ascii=False, indent=2))]

    if name == "classify_papers":
        d = _latest_output_dir()
        if not d:
            return [TextContent(type="text", text=json.dumps({"error": "No data yet"}))]
        papers = _read_papers(d)
        classified = classify_papers(papers)
        Path(d / "papers.json").write_text(
            json.dumps(classified, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        monetary_count = sum(1 for p in classified if p.get("is_monetary"))
        return [TextContent(type="text", text=json.dumps({
            "total": len(classified),
            "monetary_related": monetary_count,
            "sample": classified[0] if classified else None,
        }, ensure_ascii=False, indent=2))]

    if name == "setup_feishu":
        webhook = arguments.get("webhook_url", "")
        if not webhook:
            return [TextContent(type="text", text=json.dumps({"error": "webhook_url required"}))]
        import json as _json
        cfg_path = ROOT / "config.json"
        cfg = _json.loads(cfg_path.read_text(encoding="utf-8"))
        cfg.setdefault("push", {})["feishu_webhook"] = webhook
        cfg_path.write_text(_json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        return [TextContent(type="text", text=json.dumps({"ok": True, "message": "Feishu webhook configured"}, ensure_ascii=False))]

    raise ValueError(f"Unknown tool: {name}")


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())
