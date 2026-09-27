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

def get_tools_metadata() -> List[Dict[str, Any]]:
    """
    获取所有已注册工具的元数据定义（包含工具名、中文描述、参数 Schema 以及启用状态），
    主要用于前端页面可视化展示和用户按需查看配置。

    返回:
        List[Dict[str, Any]]: 格式化后的工具清单
    """
    metadata = []
    for t in DEFAULT_TOOLS:
        metadata.append({
            "name": t.name,
            "description": t.description,
            "args": t.args,
            "enabled": True,
        })
    return metadata
