import json
from typing import Optional

import requests


def send_feishu(webhook_url: str, content: str) -> dict:
    if not webhook_url:
        return {"ok": False, "error": "webhook URL not configured"}

    payload = {
        "msg_type": "text",
        "content": {"text": content},
    }

    try:
        resp = requests.post(webhook_url, json=payload, timeout=15)
        result = resp.json()
        return {"ok": result.get("StatusCode") == 0, "error": result.get("StatusMessage", "")}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def send_feishu_card(webhook_url: str, title: str, body: str, link: Optional[str] = None) -> dict:
    if not webhook_url:
        return {"ok": False, "error": "webhook URL not configured"}

    elements = []
    for line in body.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": line},
        })

    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": title},
            "template": "blue",
        },
        "elements": elements[:50],
    }

    payload = {
        "msg_type": "interactive",
        "card": card,
    }

    try:
        resp = requests.post(webhook_url, json=payload, timeout=15)
        result = resp.json()
        code = result.get("code", -1)
        return {"ok": code == 0, "error": result.get("msg", "")}
    except Exception as e:
        return {"ok": False, "error": str(e)}
