"""飞书交互机器人核心逻辑：指令解析 + 白名单 + 异步全文翻译 + 文件推送。"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

from ..filter import get_bot_config
from .docs import generate_fulltext_docs
from .pdf import fetch_and_extract
from ..translator import translate_fulltext

ROOT = Path(__file__).resolve().parents[3]
OUTPUT_DIR = ROOT / "outputs"

HELP_TEXT = (
    "📖 指令说明：\n"
    "• `翻译 <编号>` 全文翻译，完成后推送 Word+PDF 到本群\n"
    "• `摘要 <编号>` 查看中文摘要\n"
    "• `列表` 今日简报论文列表\n"
    "• `帮助` 显示本说明"
)


class BotState:
    """记录后台任务状态，避免重复处理相同指令。"""

    def __init__(self):
        self._active: set[str] = set()
        self._stripped: set[str] = set()  # 防止飞书重复下发事件

    def begin(self, key: str) -> bool:
        if key in self._active or key in self._stripped:
            return False
        self._active.add(key)
        self._stripped.add(key)
        return True

    def end(self, key: str):
        self._active.discard(key)


class FeishuBot:
    def __init__(self, client, sender, app_id: str, app_secret: str,
                 allowlist: list[str] | None = None):
        self.client = client
        self.sender = sender
        self.app_id = app_id
        self.app_secret = app_secret
        self.allowlist = allowlist or []
        self.state = BotState()

    def is_allowed(self, open_id: str) -> bool:
        return "*" in self.allowlist or open_id in self.allowlist

    async def handle_message(self, chat_id: str, open_id: str, text: str) -> str | None:
        if not self.is_allowed(open_id):
            return "⛔ 无权限使用本机器人。"
        stripped = re.sub(r"^@[^\s@]+\s*", "", text.strip()).strip()
        if not stripped:
            return None

        cmd, _, arg = stripped.partition(" ")
        cmd = cmd.strip()
        arg = arg.strip()

        if cmd in ("帮助", "help", "菜单"):
            return HELP_TEXT
        if cmd in ("列表", "list"):
            return self._list_papers()
        if cmd in ("摘要", "abstract"):
            return self._abstract(open_id, arg)
        if cmd in ("翻译", "translate"):
            return self._translate(chat_id, open_id, arg)
        return "未知指令，发送 `帮助` 查看说明。"

    # ---------- 列表 ----------
    def _list_papers(self) -> str:
        papers = _load_latest_papers()
        if not papers:
            return "暂无简报数据。"
        papers = _sorted_papers(papers)
        lines = ["📋 最新简报论文列表（回复 `翻译 <编号>` 全文翻译）："]
        for i, p in enumerate(papers, 1):
            mark = "🔴" if p.get("is_monetary") else ""
            lines.append(f"{i}. {mark} {p.get('title_zh') or p.get('title')}")
        return "\n".join(lines[:50])

    # ---------- 摘要 ----------
    def _abstract(self, open_id: str, arg: str) -> str | None:
        idx = _parse_idx(arg)
        if idx is None:
            return "格式：`摘要 <编号>`"
        paper = _get_paper(idx)
        if paper is None:
            return f"未找到编号 {idx}，发送 `列表` 查看。"
        zh = paper.get("abstract_zh")
        if zh:
            return f"{idx}. {paper.get('title_zh') or paper.get('title')}\n\n{zh}"
        en = paper.get("abstract")
        if en:
            return f"{idx}. {paper.get('title_zh') or paper.get('title')}\n\n（暂无中文摘要）\n{en[:500]}"
        return f"{idx}. {paper.get('title_zh') or paper.get('title')}\n\n（本文无摘要）"

    # ---------- 全文翻译（异步） ----------
    def _translate(self, chat_id: str, open_id: str, arg: str) -> str | None:
        idx = _parse_idx(arg)
        if idx is None:
            return "格式：`翻译 <编号>`"
        paper = _get_paper(idx)
        if paper is None:
            return f"未找到编号 {idx}，发送 `列表` 查看。"

        key = f"{chat_id}:{idx}"
        if not self.state.begin(key):
            return "该翻译任务已在处理中，请稍候。"
        asyncio.ensure_future(self._translate_worker(chat_id, key, paper))
        return f"📝 开始全文翻译《{paper.get('title_zh') or paper.get('title')}》，完成后将推送 Word+PDF 至本群，请稍候。"

    async def _translate_worker(self, chat_id: str, key: str, paper: dict):
        try:
            await self.sender.send(chat_id, f"🔍 正在下载原文献并全文翻译，较长论文约需数分钟…")
            result = await asyncio.to_thread(self._do_fulltext, paper)
            if result.get("error"):
                await self.sender.send(chat_id, f"⚠️ 翻译失败：{result['error']}")
                return
            await self.sender.send(chat_id, result["ack"])
            for fp in result.get("files", []):
                ok, msg = await self._send_file(chat_id, fp)
                print(f"[FILE] {fp.name} ok={ok} {msg}", flush=True)
                if not ok:
                    await self.sender.send(chat_id, f"⚠️ 文件 {fp.name} 上传失败：{msg}")
        except Exception as e:
            print(f"[WORKER] error: {e}", flush=True)
            await self.sender.send(chat_id, f"⚠️ 翻译处理出错：{e}")
        finally:
            self.state.end(key)

    def _do_fulltext(self, paper: dict) -> dict:
        text, source = fetch_and_extract(paper)
        if text is None:
            return {"error": f"原文下载失败：{source}"}
        print(f"[FULLTEXT] translating {len(text)} chars...", flush=True)
        translated = translate_fulltext(text)
        docs = generate_fulltext_docs(paper, translated, OUTPUT_DIR)
        if not docs:
            return {"error": "文档生成失败"}
        title = paper.get("title_zh") or paper.get("title")
        if source.startswith("abstract:"):
            ack = f"✅《{title}》原文 PDF 不可用，已翻译其英文摘要并推送 Word 与 PDF。"
        else:
            ack = f"✅《{title}》全文翻译完成，已推送 Word 与 PDF。"
        return {
            "ack": ack,
            "files": docs,
        }

    async def _send_file(self, chat_id: str, path: Path) -> tuple[bool, str]:
        try:
            from lark_oapi.api.im.v1 import (
                CreateFileRequest, CreateFileRequestBody,
                CreateMessageRequest, CreateMessageRequestBody,
            )
            with open(path, "rb") as f:
                file_bytes = f.read()
            req = CreateFileRequest.builder() \
                .request_body(CreateFileRequestBody.builder()
                              .file_type("pdf" if path.suffix.lower() == ".pdf" else "doc")
                              .file_name(path.name)
                              .file(file_bytes)
                              .build()) \
                .build()
            resp = self.client.im.v1.file.create(req)
            if resp.code != 0:
                return False, f"{resp.code} {resp.msg}"
            file_key = resp.data.file_key
            content = json.dumps({"file_key": file_key}, ensure_ascii=False)
            msg_req = CreateMessageRequest.builder() \
                .receive_id_type("chat_id") \
                .request_body(CreateMessageRequestBody.builder()
                              .receive_id(chat_id)
                              .msg_type("file")
                              .content(content)
                              .build()) \
                .build()
            msg_resp = self.client.im.v1.message.create(msg_req)
            if msg_resp.code != 0:
                return False, f"{msg_resp.code} {msg_resp.msg}"
            return True, "ok"
        except Exception as e:
            return False, str(e)


def _parse_idx(arg: str) -> int | None:
    if not arg:
        return None
    try:
        idx = int(arg)
        return idx if idx >= 1 else None
    except ValueError:
        return None


def _load_latest_papers() -> list[dict]:
    if not OUTPUT_DIR.exists():
        return []
    dirs = sorted([d for d in OUTPUT_DIR.iterdir() if d.is_dir()], reverse=True)
    for d in dirs:
        fp = d / "papers.json"
        if fp.exists():
            try:
                return json.loads(fp.read_text(encoding="utf-8"))
            except Exception:
                continue
    return []


def _sorted_papers(papers: list[dict]) -> list[dict]:
    def key(p):
        return (1 if p.get("is_monetary") else 0, p.get("published", ""))
    return sorted(papers, key=key)


def _get_paper(idx: int) -> dict | None:
    papers = _sorted_papers(_load_latest_papers())
    if 1 <= idx <= len(papers):
        return papers[idx - 1]
    return None