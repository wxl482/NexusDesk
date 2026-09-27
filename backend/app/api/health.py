from fastapi import APIRouter
from app.core.config import settings

router = APIRouter(tags=["服务健康检查"])

@router.get("/health")
async def health_check():
    """
    供 Electron 主进程或监控系统轮询探测的健康检查接口。
    当返回 HTTP 200 且 status="ok" 时，说明 Python 后端服务已就绪。
    """
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.VERSION,
    }
