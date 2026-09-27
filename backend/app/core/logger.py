import sys
import logging
from pathlib import Path
from loguru import logger
from app.core.config import settings

class InterceptHandler(logging.Handler):
    """
    拦截 Python 标准库 logging 的日志，统一重定向转发给 Loguru 输出
    实现 Uvicorn、FastAPI、LangChain 等库日志的风格统一与文件持久化
    """
    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # 向上追溯查找真实的日志调用堆栈帧，确保显示正确的文件名与行号
        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def setup_logging():
    """
    初始化全局日志系统：
    1. 移除默认 Handler
    2. 配置终端多彩控制台输出
    3. 配置文件输出（应用全量日志按日轮转 + 异常日志单独存档）
    4. 劫持 Uvicorn、FastAPI 及标准库日志
    """
    # 清空所有已有处理器，避免重复打印
    logger.remove()

    # 1. 控制台彩色输出格式
    console_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>"
    )
    logger.add(
        sys.stdout,
        level=settings.LOG_LEVEL,
        format=console_format,
        colorize=True,
    )

    # 2. 配置文件输出（按天轮转、保留10天、异步队列写入保证性能）
    log_dir = settings.LOG_PATH
    log_dir.mkdir(parents=True, exist_ok=True)

    file_format = (
        "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
        "{level: <8} | "
        "{name}:{function}:{line} - "
        "{message}"
    )

    # 2.1 全量应用日志 (INFO及以上)
    logger.add(
        str(log_dir / "app_{time:YYYY-MM-DD}.log"),
        rotation=settings.LOG_ROTATION,
        retention=settings.LOG_RETENTION,
        level="INFO",
        format=file_format,
        encoding="utf-8",
        enqueue=True,
    )

    # 2.2 错误日志专用归档 (ERROR及以上，附带完整异常堆栈分析)
    logger.add(
        str(log_dir / "error_{time:YYYY-MM-DD}.log"),
        rotation=settings.LOG_ROTATION,
        retention="30 days",
        level="ERROR",
        format=file_format,
        encoding="utf-8",
        enqueue=True,
        backtrace=True,
        diagnose=True,
    )

    # 3. 劫持标准库 logging 及 Uvicorn 相关日志
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    for uvicorn_logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
        _logger = logging.getLogger(uvicorn_logger_name)
        _logger.handlers = [InterceptHandler()]
        _logger.propagate = False

    logger.info("✅ 日志系统初始化完成，已开启控制台彩显与文件持久化轮转")


__all__ = ["logger", "setup_logging"]
