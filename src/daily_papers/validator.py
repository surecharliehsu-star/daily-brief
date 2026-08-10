import json
from datetime import datetime, timedelta
from typing import Any
from .filter import get_ai_config

FILTER_DAYS = 7


def validate_papers(
    papers: list[dict],
    ai_ready: bool = True,
    filter_days: int = FILTER_DAYS,
) -> tuple[list[dict], list[dict]]:
    """Return (passed, filtered) after date filter + optional AI audit."""
    passed, filtered = _date_filter(papers, filter_days)
    if ai_ready:
        passed, ai_filtered = _ai_audit(passed)
        filtered.extend(ai_filtered)
    return passed, filtered


def _date_filter(papers: list[dict], days: int) -> tuple[list[dict], list[dict]]:
    """Remove papers older than `days` from today."""
    now = datetime.now()
    cutoff = now - timedelta(days=days)
    passed, filtered = [], []
    for p in papers:
        pub = p.get("published", "")
        if not pub:
            passed.append(p)
            continue
        try:
            dt = datetime.fromisoformat(pub) if "T" in pub else datetime.strptime(pub[:10], "%Y-%m-%d")
        except (ValueError, IndexError):
            passed.append(p)
            continue
        if dt >= cutoff:
            passed.append(p)
        else:
            p["_filter_reason"] = f"日期超过{days}天"
            filtered.append(p)
    return passed, filtered


def _ai_audit(papers: list[dict]) -> tuple[list[dict], list[dict]]:
    """Batch AI audit: check title, abstract, URL completeness and plausibility."""
    ai_cfg = get_ai_config()
    api_key = ai_cfg.get("api_key", "")
    if not api_key:
        return papers, []

    from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url=ai_cfg.get("base_url", "https://api.deepseek.com/v1"))

    papers_for_audit = []
    for p in papers:
        papers_for_audit.append({
            "idx": len(papers_for_audit),
            "title": p.get("title", ""),
            "title_zh": p.get("title_zh", ""),
            "source": p.get("source", ""),
            "published": p.get("published", ""),
            "url": p.get("url", ""),
        })

    prompt = f"""你是一个学术论文审核助手。检查以下论文列表，找出有问题的条目。
当前日期: {datetime.now().strftime("%Y-%m-%d")}

问题类型:
- bad_date: 日期明显不合理（如年份不符、未来日期等），但已被7天过滤排除的不算
- bad_title: 标题乱码、空、明显不是学术论文（如会议通知、新闻稿）
- bad_url: URL为空或明显无效
- duplicate: 与列表中另一篇论文内容重复（给出另一个idx）

对每篇有问题的论文，返回:
{{"idx": 数字, "issue": "问题类型", "reason": "简短中文原因"}}

如果全部正常，返回空列表 []。

论文列表:
{json.dumps(papers_for_audit, ensure_ascii=False, indent=2)}"""

    try:
        resp = client.chat.completions.create(
            model=ai_cfg.get("model", "deepseek-chat"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=2000,
            extra_body={"thinking": {"type": "disabled"}},
        )
        content = resp.choices[0].message.content.strip()
        start = content.find("[")
        end = content.rfind("]") + 1
        if start != -1 and end > start:
            issues = json.loads(content[start:end])
        else:
            issues = []
    except Exception:
        return papers, []

    import re
    reject_idxs = {i["idx"] for i in issues}

    dupe_pairs = []
    for i in issues:
        if i.get("issue") == "duplicate":
            nums = re.findall(r'\d+', i.get("reason", ""))
            if nums:
                other = int(nums[0])
                if other != i["idx"]:
                    dupe_pairs.append((i["idx"], other))

    for a, b in dupe_pairs:
        keep, remove = min(a, b), max(a, b)
        reject_idxs.discard(keep)

    passed, filtered = [], []
    for idx, p in enumerate(papers):
        if idx in reject_idxs:
            reason = next((i["reason"] for i in issues if i["idx"] == idx), "AI审核未通过")
            p["_filter_reason"] = reason
            filtered.append(p)
        else:
            passed.append(p)
    return passed, filtered
