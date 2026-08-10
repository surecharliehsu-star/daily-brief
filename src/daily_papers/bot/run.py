"""飞书交互机器人入口：lark-oapi 长连接常驻进程。

用法：
  python -m src.daily_papers.bot.run          # 连接飞书（需 config.json bot 配置）
  python -m src.daily_papers.bot.run --check  # 自检（不连接）
"""
from __future__ import annotations

import asyncio
import json
import sys

from ..filter import get_bot_config, _load_config


def _extract_text(content: str) -> str:
    try:
        return json.loads(content).get("text", "")
    except Exception:
        return ""


def make_sender(client):
    from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody

    class Sender:
        async def send(self, chat_id: str, text: str):
            content = json.dumps({"text": text}, ensure_ascii=False)
            req = CreateMessageRequest.builder() \
                .receive_id_type("chat_id") \
                .request_body(CreateMessageRequestBody.builder()
                              .receive_id(chat_id)
                              .msg_type("text")
                              .content(content)
                              .build()) \
                .build()
            resp = await client.im.v1.message.acreate(req)
            print(f"[SEND] to={chat_id} code={resp.code} text={text[:40]!r}", flush=True)

    return Sender()


def run_real(bot_cfg: dict):
    from lark_oapi import Client as LarkClient, EventDispatcherHandler
    from lark_oapi.ws import Client as WsClient

    from .feishu_bot import FeishuBot

    client = LarkClient.builder().app_id(bot_cfg["app_id"]).app_secret(bot_cfg["app_secret"]).build()
    bot = FeishuBot(
        client,
        make_sender(client),
        bot_cfg["app_id"],
        bot_cfg["app_secret"],
        allowlist=bot_cfg.get("allowed_approvers", []),
    )

    async def _handle(payload: dict):
        reply = await bot.handle_message(payload["chat_id"], payload["open_id"], payload["text"])
        if reply:
            await bot.sender.send(payload["chat_id"], reply)

    def on_message(data):
        event = data.event
        msg = event.message
        chat_type = msg.chat_type if msg.chat_type in ("p2p", "group") else "p2p"
        if chat_type != "group":
            return
        payload = {
            "chat_id": msg.chat_id,
            "open_id": event.sender.sender_id.open_id,
            "text": _extract_text(msg.content),
        }
        print(f"[EVENT] {payload['open_id']} in {payload['chat_id']}: {payload['text']!r}", flush=True)
        if not payload["text"].strip():
            return
        asyncio.create_task(_handle(payload))

    handler = EventDispatcherHandler.builder("", "") \
        .register_p2_im_message_receive_v1(on_message) \
        .build()
    ws_client = WsClient(bot_cfg["app_id"], bot_cfg["app_secret"], event_handler=handler)
    print("[BOT] 已启动，等待飞书群消息...", flush=True)
    ws_client.start()


def run_check():
    print("[CHECK] 依赖与配置自检")
    try:
        from lark_oapi import Client as _  # noqa: F401
        print("  lark_oapi: OK")
    except Exception as e:
        print(f"  lark_oapi: FAIL {e}")
    try:
        import fitz  # noqa: F401
        print("  pymupdf: OK")
    except Exception as e:
        print(f"  pymupdf: FAIL {e}")
    try:
        from docx import Document  # noqa: F401
        print("  python-docx: OK")
    except Exception as e:
        print(f"  python-docx: FAIL {e}")
    try:
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont  # noqa: F401
        print("  reportlab: OK")
    except Exception as e:
        print(f"  reportlab: FAIL {e}")


def main():
    if "--check" in sys.argv:
        run_check()
        return
    cfg = get_bot_config()
    if not cfg.get("app_id") or not cfg.get("app_secret"):
        print("未配置 bot.app_id / bot.app_secret（config.json），退出", file=sys.stderr)
        sys.exit(1)
    run_real(cfg)


if __name__ == "__main__":
    main()