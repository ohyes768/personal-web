"""
DeepSeek chat completions 调用（httpx，带超时；失败由调用方落 failed）。
"""
from __future__ import annotations

import httpx

from src.config import (
    get_deepseek_api_key,
    get_deepseek_base_url,
    get_deepseek_model,
    get_deepseek_timeout,
)


def generate_summary(prompt: str) -> str:
    """同步阻塞调用 DeepSeek；失败抛 httpx.HTTPError / RuntimeError。"""
    api_key = get_deepseek_api_key()
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY not configured")
    url = f"{get_deepseek_base_url()}/chat/completions"
    resp = httpx.post(
        url,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": get_deepseek_model(),
            "messages": [
                {"role": "system", "content": "你是工作日报撰写助手，用中文输出 markdown 总结。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
        },
        timeout=get_deepseek_timeout(),
    )
    resp.raise_for_status()
    data = resp.json()
    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    if not content:
        raise RuntimeError("DeepSeek returned empty content")
    return content
