import os
import sys
# 保证 numpy 模块在所有底层 AI/向量库之前完成全局顶层初始化，避免 Python 3.11 下的内部循环导入问题
import numpy

# 兼容 macOS / Linux 环境中 IPv6 地址（::1）导致 httpx InvalidURL 异常的已知系统环境变量缺陷
for _env_key in ["NO_PROXY", "no_proxy"]:
    _val = os.environ.get(_env_key)
    if _val and "::" in _val:
        os.environ[_env_key] = ",".join([p.strip() for p in _val.split(",") if not p.strip().startswith("::")])

import argparse
from contextlib import asynccontextmanager
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core import settings, logger, setup_logging, setup_request_logging_middleware
from app.api import api_router

# 初始化全局日志系统（劫持标准库 logging 并开启 Loguru 终端彩显与文件轮转）
setup_logging()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理：服务启动与平滑关闭"""
    logger.info(f"🚀 {settings.APP_NAME} 服务启动就绪 (v{settings.VERSION})")
    yield
    logger.info(f"🛑 {settings.APP_NAME} 服务正在安全关闭...")

# 实例化 FastAPI 核心应用
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    description="基于 Python + LangChain / LangGraph 的 NexusDesk 智能体桌面工作台推理引擎",
    lifespan=lifespan,
)

# 配置跨域中间件 (CORS)，允许来自 Electron 渲染进程和 Vite 开发环境的跨源请求
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 配置全链路请求监控与耗时统计中间件
setup_request_logging_middleware(app)

# 挂载业务路由中心
app.include_router(api_router)

@app.get("/")
def root():
    """根路径引导探针与文档跳转说明"""
    return {
        "name": settings.APP_NAME,
        "version": settings.VERSION,
        "status": "online",
        "docs_url": "/docs",
    }

def start():
    """
    服务启动主入口函数。支持通过命令行参数动态传入监听端口与主机地址，
    方便 Electron 主进程根据空闲端口进行动态启动与管理。
    """
    parser = argparse.ArgumentParser(description="Multi-Functional Agent 后端服务启动器")
    parser.add_argument("--port", type=int, default=settings.PORT, help="FastAPI 服务监听端口")
    parser.add_argument("--host", type=str, default=settings.HOST, help="FastAPI 服务监听主机地址")
    parser.add_argument("--reload", action=argparse.BooleanOptionalAction, default=settings.DEBUG, help="是否开启代码变动热重载")
    parser.add_argument("--access-log", action=argparse.BooleanOptionalAction, default=True, help="是否开启 Uvicorn 底层访问日志")
    args = parser.parse_args()

    logger.info(f"🚀 正在启动 {settings.APP_NAME} v{settings.VERSION}，访问地址: http://{args.host}:{args.port}")
    if args.reload:
        uvicorn.run(
            "main:app",
            host=args.host,
            port=args.port,
            reload=True,
            reload_dirs=["app"],  # 严格限制仅监听 app 目录，防止 Agent 在根目录或工作区创建脚本/文件导致服务被热重载强制终止中断 SSE
            access_log=args.access_log,
        )
    else:
        uvicorn.run(
            "main:app",
            host=args.host,
            port=args.port,
            reload=False,
            access_log=args.access_log,
        )

if __name__ == "__main__":
    start()
