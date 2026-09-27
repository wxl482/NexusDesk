from fastapi import APIRouter
from app.tools.base import get_tools_metadata

router = APIRouter(prefix="/api/tools", tags=["工具注册中心"])

@router.get("")
async def list_tools():
    """
    获取系统中所有已注册 Agent 工具的元数据列表（含工具名、描述和参数 Schema）。
    """
    return {"tools": get_tools_metadata()}
