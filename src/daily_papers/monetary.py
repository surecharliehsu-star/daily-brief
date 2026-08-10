import json
from typing import Optional

from openai import OpenAI

from .filter import get_ai_config, _load_config

SYSTEM_PROMPT = """You are an economics classifier. For each paper title, determine if it is related to MONETARY POLICY.
Monetary policy includes: interest rates, inflation, QE/QT, central bank tools, forward guidance, CBDC, exchange rate policy, monetary transmission, reserve requirements, liquidity facilities.

Return a JSON array of objects, one per paper in order: [{"is_monetary": true/false, "reason": "brief reason"}, ...]"""


def _get_keywords() -> list[str]:
    cfg = _load_config()
    return cfg.get("monetary_policy", {}).get("keywords", [])


def _keyword_match(title: str, abstract: str) -> bool:
    keywords = _get_keywords()
    text = (title + " " + abstract).lower()
    for kw in keywords:
        if kw.lower() in text:
            return True
    return False


def _build_client() -> Optional[OpenAI]:
    cfg = get_ai_config()
    if not cfg.get("enabled") or not cfg.get("api_key"):
        return None
    return OpenAI(
        api_key=cfg["api_key"],
        base_url=cfg.get("base_url", "https://api.deepseek.com/v1"),
    )


def _classify_batch(titles: list[str], abstracts: list[str]) -> list[dict]:
    client = _build_client()
    if client is None:
        return [{"is_monetary": False, "reason": "AI not configured"} for _ in titles]

    if not titles:
        return []

    text = "\n".join(f"{i+1}. Title: {t}\n   Abstract: {a[:200]}" for i, (t, a) in enumerate(zip(titles, abstracts)))
    try:
        resp = client.chat.completions.create(
            model=get_ai_config().get("model", "deepseek-v4-flash"),
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            temperature=0.1,
            max_tokens=2000,
            extra_body={"thinking": {"type": "disabled"}},
        )
        result = resp.choices[0].message.content.strip()
        result = result.strip("```json").strip("```").strip()
        data = json.loads(result)
        if isinstance(data, list):
            return data[:len(titles)]
        return [data] + [{"is_monetary": False, "reason": "parse fallback"}] * (len(titles) - 1)
    except Exception:
        return [{"is_monetary": False, "reason": "classification error"} for _ in titles]


def classify_paper(title: str, abstract: str) -> dict:
    if _keyword_match(title, abstract):
        return {"is_monetary": True, "reason": "keyword match"}
    return _classify_batch([title], [abstract])[0]


def classify_papers(papers: list[dict], batch_size: int = 20) -> list[dict]:
    results = list(papers)
    to_classify_idx = []
    to_classify_titles = []
    to_classify_abstracts = []

    for i, p in enumerate(results):
        if p.get("is_monetary"):
            continue
        if _keyword_match(p.get("title", ""), p.get("abstract", "")):
            results[i]["is_monetary"] = True
        else:
            to_classify_idx.append(i)
            to_classify_titles.append(p.get("title", ""))
            to_classify_abstracts.append(p.get("abstract", ""))

    for start in range(0, len(to_classify_titles), batch_size):
        batch_titles = to_classify_titles[start:start + batch_size]
        batch_abstracts = to_classify_abstracts[start:start + batch_size]
        classifications = _classify_batch(batch_titles, batch_abstracts)
        for j, cls in enumerate(classifications):
            idx = to_classify_idx[start + j]
            results[idx]["is_monetary"] = cls.get("is_monetary", False)

    return results
