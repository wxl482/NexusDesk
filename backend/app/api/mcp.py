from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.mcp.manager import MCPManager

router = APIRouter(prefix="/api/mcp", tags=["Model Context Protocol (MCP 生态)"])


class MCPServerRegisterRequest(BaseModel):
    id: str = Field(..., description="MCP 服务唯一标识符")
    name: str = Field(..., description="服务展示名称")
    command: str = Field(..., description="启动命令 (如 npx 或 python3)")
    args: Optional[List[str]] = Field(default_factory=list, description="命令参数列表")
    env: Optional[Dict[str, str]] = Field(default_factory=dict, description="环境变量")
    enabled: bool = Field(default=True, description="是否立即启用")
    description: Optional[str] = Field(default="", description="服务描述")


class MCPToggleRequest(BaseModel):
    enabled: bool = Field(..., description="是否启用")


@router.get("/servers")
async def list_servers():
    """获取所有已配置的 MCP 服务列表"""
    mgr = MCPManager.get_instance()
    servers = mgr.list_servers()
    return {"servers": servers, "total": len(servers)}


@router.post("/servers")
async def register_server(req: MCPServerRegisterRequest):
    """注册或更新一个 MCP 外部协议服务"""
    mgr = MCPManager.get_instance()
    server = mgr.register_server(
        server_id=req.id,
        name=req.name,
        command=req.command,
        args=req.args,
        env=req.env,
        enabled=req.enabled,
        description=req.description or "",
    )
    return {"success": True, "server": server}


@router.delete("/servers/{server_id}")
async def delete_server(server_id: str):
    """删除指定的 MCP 服务"""
    mgr = MCPManager.get_instance()
    success = mgr.delete_server(server_id)
    if not success:
        raise HTTPException(status_code=404, detail="未找到该 MCP 服务")
    return {"success": True, "server_id": server_id}


@router.post("/servers/{server_id}/toggle")
async def toggle_server(server_id: str, req: MCPToggleRequest):
    """启用或禁用指定的 MCP 服务"""
    mgr = MCPManager.get_instance()
    success = mgr.toggle_server(server_id, req.enabled)
    if not success:
        raise HTTPException(status_code=404, detail="未找到该 MCP 服务")
    return {"success": True, "server_id": server_id, "enabled": req.enabled}


@router.post("/servers/{server_id}/probe")
async def probe_server(server_id: str):
    """通过 stdio 实时连接 MCP 服务握手并探测可用工具"""
    mgr = MCPManager.get_instance()
    tools = await mgr.probe_server_tools(server_id)
    return {"success": True, "server_id": server_id, "tools": tools, "count": len(tools)}


@router.get("/tools")
async def list_tools():
    """获取所有已启用的 MCP 服务汇集的工具元数据"""
    mgr = MCPManager.get_instance()
    tools_list = []
    for s in mgr.list_servers():
        s_id = s.get("id")
        cached = mgr._cached_tools.get(s_id, [])
        for t in cached:
            tools_list.append({
                "name": f"mcp_{s_id}_{t['name']}",
                "original_name": t["name"],
                "server_id": s_id,
                "server_name": s.get("name"),
                "description": t.get("description"),
            })
    return {"tools": tools_list, "total": len(tools_list)}
