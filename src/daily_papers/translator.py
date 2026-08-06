import json
from typing import Optional

from openai import OpenAI

from .filter import get_ai_config

TITLE_PROMPT = """You are a professional financial economics translator. Translate each English paper title to Chinese.
Requirements:
- 信达雅：准确传达原意，术语规范，符合中文金融学术表述习惯
- 输出仅中文译文，每行一条，序号与输入一致
- 专业术语保留英文缩写（如 CBDC, QE, LSAP, DSGE, VAR）
- 已有中文则原样返回"""

ABSTRACT_PROMPT = """You are a professional financial economics translator. Translate each English abstract to Chinese.
Requirements:
- 信达雅：准确传达原意，术语规范，符合中文金融学术表述习惯
- 保持原文结构、信息完整性和篇幅，注意句子之间的逻辑连贯与衔接
- 输出仅中文译文，每行一条，序号与输入一致
- 专业术语保留英文缩写"""


def _build_client() -> Optional[OpenAI]:
    cfg = get_ai_config()
    if not cfg.get("enabled") or not cfg.get("api_key"):
        return None
    return OpenAI(
        api_key=cfg["api_key"],
        base_url=cfg.get("base_url", "https://api.deepseek.com/v1"),
    )


def _translate_batch(items: list[str], prompt: str = TITLE_PROMPT, max_tokens: int = 2000) -> list[str]:
    client = _build_client()
    if client is None:
        return [""] * len(items)

    if not items:
        return []

    def _single_call(chunk: list[str]) -> list[str]:
        text = "\n".join(f"{i+1}. {t}" for i, t in enumerate(chunk))
        resp = client.chat.completions.create(
            model=get_ai_config().get("model", "deepseek-v4-flash"),
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": text},
            ],
            temperature=0.1,
            max_tokens=max_tokens,
        )
        result = resp.choices[0].message.content.strip()
        lines = [l.strip() for l in result.split("\n") if l.strip()]
        translations = []
        for line in lines:
            line = line.lstrip("0123456789. ")
            line = line.strip("\"'")
            translations.append(line)
        while len(translations) < len(chunk):
            translations.append("")
        return translations[: len(chunk)]

    result_holder = [""] * len(items)
    # 先整批翻译
    try:
        batch_results = _single_call(items)
        for i, zh in enumerate(batch_results):
            result_holder[i] = zh
    except Exception:
        pass

    # 对失败(空)项逐条重试一次
    for i in range(len(items)):
        if result_holder[i].strip():
            continue
        try:
            one = _single_call([items[i]])
            result_holder[i] = one[0]
        except Exception:
            result_holder[i] = ""
    return result_holder


def translate_title(title: str) -> str:
    return _translate_batch([title], prompt=TITLE_PROMPT)[0]


def translate_titles(papers: list[dict], batch_size: int = 10) -> list[dict]:
    results = list(papers)
    to_translate = []
    indices = []
    for i, p in enumerate(results):
        if not p.get("title_zh") and p.get("title"):
            to_translate.append(p["title"])
            indices.append(i)

    for start in range(0, len(to_translate), batch_size):
        batch = to_translate[start : start + batch_size]
        translations = _translate_batch(batch, prompt=TITLE_PROMPT)
        for j, zh in enumerate(translations):
            results[indices[start + j]]["title_zh"] = zh

    return results


def translate_abstracts(papers: list[dict], monetary_only: bool = True, batch_size: int = 5) -> list[dict]:
    results = list(papers)
    to_translate = []
    indices = []
    for i, p in enumerate(results):
        if monetary_only and not p.get("is_monetary"):
            continue
        if not p.get("abstract_zh") and p.get("abstract"):
            to_translate.append(p["abstract"])
            indices.append(i)

    if not to_translate:
        return results

    print(f"  Translating {len(to_translate)} abstracts...")
    for start in range(0, len(to_translate), batch_size):
        batch = to_translate[start : start + batch_size]
        translations = _translate_batch(batch, prompt=ABSTRACT_PROMPT, max_tokens=3000)
        for j, zh in enumerate(translations):
            results[indices[start + j]]["abstract_zh"] = zh

    zh_count = sum(1 for p in results if p.get("abstract_zh"))
    print(f"  Abstract translations: {zh_count}/{len(to_translate)}")
    return results
