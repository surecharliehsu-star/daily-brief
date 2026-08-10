import json
import re
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = ROOT / "config.json"


def _load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return {"keywords": {"zh": [], "en": []}, "ai_scoring": {"enabled": False}}


def _save_config(cfg: dict):
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def get_keywords() -> list[str]:
    cfg = _load_config()
    kws = cfg.get("keywords", {})
    return kws.get("en", []) + kws.get("zh", [])


def set_keywords(en: Optional[list[str]] = None, zh: Optional[list[str]] = None):
    cfg = _load_config()
    if "keywords" not in cfg:
        cfg["keywords"] = {}
    if en is not None:
        cfg["keywords"]["en"] = en
    if zh is not None:
        cfg["keywords"]["zh"] = zh
    _save_config(cfg)


def get_ai_config() -> dict:
    cfg = _load_config()
    return cfg.get("ai_scoring", {"enabled": False})


def get_bot_config() -> dict:
    cfg = _load_config()
    return cfg.get("bot", {})


def set_ai_config(**kwargs):
    cfg = _load_config()
    if "ai_scoring" not in cfg:
        cfg["ai_scoring"] = {}
    cfg["ai_scoring"].update(kwargs)
    _save_config(cfg)


def match_paper(paper: dict, keywords: list[str]) -> tuple[bool, list[str]]:
    text = " ".join([
        paper.get("title", ""),
        paper.get("abstract", ""),
        " ".join(paper.get("topics", [])),
    ]).lower()

    matched = []
    for kw in keywords:
        if kw.lower() in text:
            matched.append(kw)
    return len(matched) > 0, matched


class KeywordFilter:
    def __init__(self, keywords: Optional[list[str]] = None):
        self.keywords = keywords or get_keywords()

    def filter(self, papers: list[dict]) -> list[dict]:
        results = []
        for p in papers:
            matched, hits = match_paper(p, self.keywords)
            results.append({
                **p,
                "_matched": matched,
                "_keywords_hit": hits,
                "_keyword_count": len(hits),
            })
        return results
