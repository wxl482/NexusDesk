from typing import List, Dict, Any
from langchain_core.tools import BaseTool

from .search import web_search
from .python_exec import execute_python_code
from .terminal import execute_terminal_command
from .file_ops import (
    read_local_file,
    write_local_file,
    list_local_directory,
    delete_local_file,
)
from app.rag.vector_engine import query_knowledge_base

# 系统默认注册的所有可用工具列表
# LangGraph Agent 启动时会自动绑定该工具箱
DEFAULT_TOOLS: List[BaseTool] = [
    execute_terminal_command,
    read_local_file,
    write_local_file,
    list_local_directory,
    delete_local_file,
    web_search,
    execute_python_code,
    query_knowledge_base,
]

def get_all_tools() -> List[BaseTool]:
    """
    获取全局可用工具集合：包含内置系统工具与所有已启用的 MCP 外部生态工具。
    """
    try:
        from app.mcp.manager import MCPManager
        mcp_tools = MCPManager.get_instance().get_langchain_tools()
        return DEFAULT_TOOLS + mcp_tools
    except Exception:
        return list(DEFAULT_TOOLS)


def get_tools_metadata() -> List[Dict[str, Any]]:
    """
    获取所有已注册工具的元数据定义（包含工具名、中文描述、参数 Schema 以及启用状态），
    主要用于前端页面可视化展示和用户按需查看配置。

    返回:
        List[Dict[str, Any]]: 格式化后的工具清单
    """
    tools = get_all_tools()
    metadata = []
    for t in tools:
        is_mcp = hasattr(t, "server_id")
        metadata.append({
            "name": t.name,
            "description": t.description,
            "args": t.args if hasattr(t, "args") else {},
            "enabled": True,
            "is_mcp": is_mcp,
            "server_id": getattr(t, "server_id", None),
        })
    return metadata
