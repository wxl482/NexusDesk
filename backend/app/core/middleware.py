import time
import uuid
from typing import Callable
from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.logger import logger


def get_client_ip(request: Request) -> str:
    """获取客户端真实 IP（优先获取反向代理注入的 X-Forwarded-For / X-Real-IP）"""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    if request.client:
        return request.client.host
    return "unknown"


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    全链路请求监控中间件：
    1. 为每个请求注入或生成全局唯一 X-Request-ID
    2. 记录请求方法、URL、客户端真实 IP、Query 参数
    3. 精准测量请求处理耗时（毫秒级）
    4. 自动在响应 Header 中回写 X-Request-ID 与 X-Process-Time
    5. 按状态码分级输出日志（2xx/3xx -> INFO, 4xx -> WARNING, 5xx -> ERROR）
    6. 捕获未处理异常并记录堆栈
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 1. 唯一请求追踪 ID（如果有上游传入则透传，否则自动生成 12 位十六进制短 ID）
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        request.state.request_id = request_id

        client_ip = get_client_ip(request)
        url_path = request.url.path
        if request.url.query:
            url_path = f"{url_path}?{request.url.query}"

        start_time = time.perf_counter()

        # 2. 打印请求进入日志
        logger.info(f"[{request_id}] ➡️  {request.method} {url_path} (Client: {client_ip})")

        # 3. 处理请求并测速
        try:
            response = await call_next(request)
        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error(
                f"[{request_id}] ❌ {request.method} {url_path} | 未捕获异常: {exc} | 耗时: {duration_ms:.2f}ms"
            )
            raise exc

        duration_ms = (time.perf_counter() - start_time) * 1000

        # 4. 回写响应头方便客户端调试与链路定位
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time"] = f"{duration_ms:.2f}ms"

        # 5. 根据响应状态码分级记录完成日志
        status_code = response.status_code
        log_msg = f"[{request_id}] ⬅️  {request.method} {url_path} | 状态码: {status_code} | 耗时: {duration_ms:.2f}ms"

        if status_code >= 500:
            logger.error(log_msg)
        elif status_code >= 400:
            logger.warning(log_msg)
        else:
            logger.info(log_msg)

        return response


def setup_request_logging_middleware(app: FastAPI):
    """向 FastAPI 应用挂载请求监控中间件"""
    app.add_middleware(RequestLoggingMiddleware)
