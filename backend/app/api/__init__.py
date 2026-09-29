from fastapi import APIRouter
from .chat import router as chat_router
from .rag import router as rag_router
from .tools import router as tools_router
from .models import router as models_router
from .health import router as health_router
from .mcp import router as mcp_router

# 聚合所有业务子模块路由
api_router = APIRouter()
api_router.include_router(chat_router)
api_router.include_router(rag_router)
api_router.include_router(tools_router)
api_router.include_router(models_router)
api_router.include_router(health_router)
api_router.include_router(mcp_router)

__all__ = ["api_router"]
