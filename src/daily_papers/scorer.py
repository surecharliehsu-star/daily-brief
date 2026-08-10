import json
from typing import Optional

from openai import OpenAI

from .filter import get_ai_config, get_keywords

SYSTEM_PROMPT = """你是一个经济研究筛选助手。请根据用户的兴趣领域给论文打分（1-5分）。

兴趣领域：{keywords}

评分标准：
5 - 高度相关，直接涉及核心兴趣领域，有实质性贡献
4 - 相关，涉及兴趣领域
3 - 部分相关，间接涉及
2 - 弱相关，仅简要提及
1 - 不相关

返回严格的 JSON 格式：{{"score": <int>, "reason": "<一句话理由>"}}"""


def _build_client() -> Optional[OpenAI]:
    cfg = get_ai_config()
    if not cfg.get("enabled") or not cfg.get("api_key"):
        return None
    return OpenAI(
        api_key=cfg["api_key"],
        base_url=cfg.get("base_url", "https://api.deepseek.com/v1"),
    )


def score_paper(title: str, abstract: str, keywords: Optional[list[str]] = None) -> dict:
    client = _build_client()
    if client is None:
        return {"score": 0, "reason": "AI scoring not configured"}

    kws = keywords or get_keywords()
    kw_text = "、".join(kws[:20])

    try:
        resp = client.chat.completions.create(
            model=get_ai_config().get("model", "deepseek-chat"),
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT.format(keywords=kw_text)},
                {"role": "user", "content": f"论文标题：{title}\n摘要：{abstract[:1000]}"},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=500,
            extra_body={"thinking": {"type": "disabled"}},
        )
        result = json.loads(resp.choices[0].message.content)
        return {
            "score": max(1, min(5, int(result.get("score", 3)))),
            "reason": result.get("reason", ""),
        }
    except Exception as e:
        return {"score": 0, "reason": f"AI scoring error: {e}"}


async def score_papers(papers: list[dict]) -> list[dict]:
    results = []
    for p in papers:
        if not p.get("_matched", False):
            results.append({**p, "_ai_score": 0, "_ai_reason": "skipped (no keyword match)"})
            continue
        score = score_paper(p.get("title", ""), p.get("abstract", ""))
        results.append({**p, "_ai_score": score["score"], "_ai_reason": score["reason"]})
    return results
