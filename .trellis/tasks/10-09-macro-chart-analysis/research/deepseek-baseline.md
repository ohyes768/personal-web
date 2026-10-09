# DeepSeek接入核对（2026-10-10）

官方依据：
- https://api-docs.deepseek.com/api/create-chat-completion/ ：POST /chat/completions，当前列示deepseek-flash与deepseek-v4-pro，thinking可显式disabled；stream返回SSE，以[DONE]终止。实现前再次确认模型可用性，不硬编码旧别名。
- https://api-docs.deepseek.com/guides/multi_round_chat/ ：连续对话通过messages传递历史。
- https://api-docs.deepseek.com/quick_start/pricing/ ：部署时核对价格，不在本任务固定价格数字。

仓库：backend/macro/pyproject.toml已有httpx>=0.27，无需引入完整Agent框架；nginx/web.conf:226宏观API直转后端，该location没有鉴权指令，也未配置流式缓冲行为。外部网关是否已保护不能由此推断，需用户确认。
