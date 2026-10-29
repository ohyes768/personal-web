"""钉钉机器人 webhook 推送（index-trends 独立副本，按仓库惯例复制而非抽公共包）。

环境变量 INDEX_TRENDS_DINGTALK_WEBHOOK_URL 未配置时返回 False / 静默，
报告保存为 no_channel 状态，不发送。
"""
from __future__ import annotations

import os
from typing import Optional

import httpx


class DingTalkNotifier:
    def __init__(self, webhook_url: Optional[str] = None):
        self.webhook_url = (
            webhook_url
            if webhook_url is not None
            else os.getenv("INDEX_TRENDS_DINGTALK_WEBHOOK_URL", "")
        ).strip() or None

    def is_configured(self) -> bool:
        return bool(self.webhook_url)

    def send_markdown(self, title: str, text: str) -> tuple[bool, str | None]:
        """发送 markdown 消息。返回 (成功?, 错误说明)。

        未配置/发送失败均返回 False，调用方必须如实记录，不得伪报成功。
        """
        if not self.is_configured():
            return False, "channel_not_configured"
        payload = {"msgtype": "markdown", "markdown": {"title": title, "text": text}}
        try:
            resp = httpx.post(self.webhook_url, json=payload, timeout=10)
            data = resp.json()
        except Exception as e:  # noqa: BLE001 — 网络异常必须转为失败状态而非向上抛
            return False, f"exception: {e}"
        if resp.status_code == 200 and data.get("errcode") == 0:
            return True, None
        return False, f"status={resp.status_code} errcode={data.get('errcode')} errmsg={data.get('errmsg')}"
