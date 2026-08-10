import json
from typing import Optional

from openai import OpenAI

from .filter import get_ai_config
from .glossary import glossary_text

_TECHNIQUE = """翻译方法论（每一步都必须执行）：
1. 【语义骨架】先在头脑中还原原句的语义关系：谁是主动方？作用于谁？结果受什么影响？原文句子的重心（主谓宾焦点）在哪里。此步不输出，只用于指导下面两步。
2. 【名词短语整体搬运】形如 "the X of A to B" / "X of A on B" 的短语（如 the pass-through of rate hikes to lending rates）必须作为一个整体翻译为 "A向B的X" / "A对B的X"（如"利率上调向贷款利率的传导"），严禁拆散。
3. 【语序重组】按中文语序重新组织表达，不改变原意与信息完整性：
   - 后置定语/定语从句提前到被修饰名词之前；过长的定语拆成短句；
   - 被动语态改为主动表述（除非原文以被动强调受影响对象，则保留被动）；
   - 时间、程度等状语按中文习惯放置（通常置于动词之前）；
   - 介词短语、插入语归位，不要硬贴英文顺序。
4. 【分句/断句】长句按逻辑断点切成多句，用逗号/分号/句号分隔；禁止长定语堆叠（一句中修饰语超过一重就把主干先说出来）；单句超过约40字（中文）即考虑拆句。
5. 【书面语】避免"使得…"空泛连接词的无谓使用；删除原文没有的信息，不增不减。
6. 【术语】严格使用下方术语表的译名；无对应条目的专业金融术语给出规范中文译名并在首次出现时以括号保留英文原文；已保留的英文缩写（CBDC/QE/DSGE等）不译。"""

TRANSLATION_RULES = f"""{_TECHNIQUE}

【正反例参考】
- 原文: The pass-through of the recent policy rate hikes to lending rates has been, to a significant extent, muted by the buffer of excess liquidity.
- ❌ 反面（顺英文语序+空泛连接词+偏离重心）: 超额流动性形成缓冲，使得近期政策利率上调向贷款利率的传导受到相当程度的压制。
- ✅ 正面示例1（保留原句重心"传导…被削弱"，改为中文语序）: 近期政策利率上调向贷款利率的传导，在很大程度上被超额流动性的缓冲作用所削弱。
- ✅ 正面示例2（主动表述，强调缓冲的作用，语义完全一致）: 超额流动性的缓冲作用，在很大程度上削弱了近期政策利率上调向贷款利率的传导。
- 注意：示例2中"政策利率上调向贷款利率的传导"整体为一个名词短语，切不可拆成"上调到…"。"""

TITLE_PROMPT = f"""{TRANSLATION_RULES}

现在翻译英文学术论文标题。
Requirements:
- 输出仅中文译文，每行一条，序号与输入一致
- 标题保持简洁，符合中文金融学术标题习惯
- 专业术语保留英文缩写（如 CBDC, QE, LSAP, DSGE, VAR）
- 已有中文则原样返回

{glossary_text()}"""

ABSTRACT_PROMPT = f"""{TRANSLATION_RULES}

现在翻译英文学术论文摘要。
Requirements:
- 准确传达原意，信息完整，不遗漏、不添加
- 句子之间保持逻辑连贯与衔接
- 输出仅中文译文，每行一条，序号与输入一致
- 专业术语保留英文缩写

{glossary_text()}"""


def fulltext_prompt() -> str:
    """全文翻译 prompt（用于长篇论文全文，逐段分块翻译）。"""
    return f"""{TRANSLATION_RULES}

现在翻译一段英文经济学/金融学论文正文。
Requirements:
- 逐句翻译，完整传达原意；段落结构保持不变
- 保留文中的数字、年份、机构名、人名、缩写
- 公式、引用标记、参考文献格式保持原样
- 只输出译文本身，不要输出其他说明

{glossary_text()}"""


def _build_client() -> Optional[OpenAI]:
    cfg = get_ai_config()
    if not cfg.get("enabled") or not cfg.get("api_key"):
        return None
    return OpenAI(
        api_key=cfg["api_key"],
        base_url=cfg.get("base_url", "https://api.deepseek.com/v1"),
    )


def _single_call(chunk: list[str], prompt: str, max_tokens: int) -> list[str]:
    client = _build_client()
    if client is None:
        return [""] * len(chunk)

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


def _translate_batch(items: list[str], prompt: str = TITLE_PROMPT, max_tokens: int = 2000) -> list[str]:
    if not items:
        return []

    result_holder = [""] * len(items)
    # 先整批翻译
    try:
        batch_results = _single_call(items, prompt, max_tokens)
        for i, zh in enumerate(batch_results):
            result_holder[i] = zh
    except Exception:
        pass

    # 对失败(空)项逐条重试一次
    for i in range(len(items)):
        if result_holder[i].strip():
            continue
        try:
            one = _single_call([items[i]], prompt, max_tokens)
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


def translate_fulltext(text: str, chunk_size: int = 2000) -> str:
    """整篇全文翻译：按 chunk 分块，逐块调用，结果拼接。

    分块策略：按段落优先；单段超过 chunk_size 字符则按句子边界继续拆分。
    """
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for para in paragraphs:
        if current_len + len(para) + 1 <= chunk_size:
            current.append(para)
            current_len += len(para) + 1
            continue
        if current:
            chunks.append("\n".join(current))
            current, current_len = [], 0
        # 单段超长：按句拆分
        if len(para) > chunk_size:
            import re
            sentences = re.split(r"(?<=[.?!])\s+", para)
            sub: list[str] = []
            sub_len = 0
            for s in sentences:
                if sub_len + len(s) + 1 <= chunk_size:
                    sub.append(s)
                    sub_len += len(s) + 1
                else:
                    if sub:
                        chunks.append("\n".join(sub))
                        sub, sub_len = [], 0
                    chunks.append(s)
            if sub:
                chunks.append("\n".join(sub))
        else:
            chunks.append(para)

    if current:
        chunks.append("\n".join(current))

    translated = []
    for c in chunks:
        zh = _translate_batch([c], prompt=fulltext_prompt(), max_tokens=max(2000, len(c) * 2))[0]
        translated.append(zh)

    return "\n\n".join(translated)