"""结构化错误契约（design §7）。

所有业务错误统一 `{code, message, field_errors?}`，由 main.py 的异常处理器
展平为响应体。HTTP 状态码在抛出点决定。
"""

from __future__ import annotations


class ApiError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        field_errors: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.field_errors = field_errors


def bad_request(message: str, field_errors: dict[str, str] | None = None) -> ApiError:
    return ApiError(400, "invalid_request", message, field_errors)


def unauthorized(message: str = "未登录") -> ApiError:
    return ApiError(401, "unauthorized", message)


def not_found(message: str = "记录不存在") -> ApiError:
    return ApiError(404, "not_found", message)


def conflict(message: str, code: str = "conflict") -> ApiError:
    return ApiError(409, code, message)


def too_large(message: str) -> ApiError:
    return ApiError(413, "payload_too_large", message)


def unavailable(message: str, code: str = "dependency_unavailable") -> ApiError:
    return ApiError(503, code, message)


def rate_limited(message: str) -> ApiError:
    return ApiError(429, "rate_limited", message)
