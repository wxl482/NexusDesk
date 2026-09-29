import os
import json
import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

from langchain_core.tools import BaseTool
from app.core.config import settings

logger = logging.getLogger(__name__)


class MCPToolWrapper(BaseTool):
    """
    将标准 MCP (Model Context Protocol) 工具封装为 LangChain / LangGraph 兼容的标准 BaseTool。
    支持在 AgentState 与 ToolNode 中无缝动态调用。
    """
    server_id: str
    mcp_tool_name: str
    raw_schema: Dict[str, Any] = Field(default_factory=dict)

    def __init__(
        self,
        name: str,
        description: str,
        server_id: str,
        mcp_tool_name: str,
        raw_schema: Optional[Dict[str, Any]] = None,
        **kwargs
    ):
        super().__init__(
            name=name,
            description=description,
            server_id=server_id,
            mcp_tool_name=mcp_tool_name,
            raw_schema=raw_schema or {},
            **kwargs
        )

    def _run(self, **kwargs) -> str:
        """同步回退运行"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, self._arun(**kwargs))
                    return future.result()
            return loop.run_until_complete(self._arun(**kwargs))
        except Exception as e:
            return f"MCP 工具执行异常: {str(e)}"

    async def _arun(self, **kwargs) -> str:
        """异步调用 MCP 服务端协议并解析执行结果"""
        mgr = MCPManager.get_instance()
        return await mgr.execute_tool(self.server_id, self.mcp_tool_name, kwargs)


class MCPManager:
    """
    【P0 MCP 协议管理中心】
    负责注册、持久化、探测与调度外部 Model Context Protocol 服务（stdio/SSE 进程协议），
    并将其动态注入到 NexusDesk LangGraph Agent 工具箱中。
    """
    _instance: Optional["MCPManager"] = None

    def __init__(self):
        self.config_dir = Path("backend/data") if Path("backend").exists() else Path("data")
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.config_dir / "mcp_servers.json"
        self._servers: Dict[str, Dict[str, Any]] = {}
        self._cached_tools: Dict[str, List[Dict[str, Any]]] = {}
        self.load_servers()

    @classmethod
    def get_instance(cls) -> "MCPManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def load_servers(self):
        """从 JSON 配置文件中读取 MCP 客户端服务配置"""
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._servers = data.get("servers", {})
            except Exception as e:
                logger.warning(f"[MCPManager] 加载配置文件失败: {e}")
                self._servers = {}
        else:
            # 预设几个常用的开箱即用示例 MCP 驱动
            self._servers = {
                "fetch": {
                    "id": "fetch",
                    "name": "Web Content Fetcher (官方 MCP)",
                    "transport": "stdio",
                    "command": "python3",
                    "args": ["-m", "mcp.server.fastmcp"],
                    "enabled": False,
                    "description": "基于官方 MCP 规范的外部网页内容与 Markdown 提取服务",
                }
            }
            self.save_servers()

    def save_servers(self):
        """将配置持久化至磁盘"""
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump({"servers": self._servers}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"[MCPManager] 保存 MCP 配置失败: {e}")

    def list_servers(self) -> List[Dict[str, Any]]:
        """获取所有已注册的 MCP 服务列表及状态"""
        return list(self._servers.values())

    def register_server(
        self,
        server_id: str,
        name: str,
        command: str,
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
        enabled: bool = True,
        description: str = "",
    ) -> Dict[str, Any]:
        """注册或更新一个 MCP 服务"""
        server_info = {
            "id": server_id,
            "name": name,
            "transport": "stdio",
            "command": command,
            "args": args or [],
            "env": env or {},
            "enabled": enabled,
            "description": description,
        }
        self._servers[server_id] = server_info
        self.save_servers()
        logger.info(f"[MCPManager] 成功注册 MCP 服务: {server_id} ({name})")
        return server_info

    def delete_server(self, server_id: str) -> bool:
        """移除指定的 MCP 服务"""
        if server_id in self._servers:
            del self._servers[server_id]
            self.save_servers()
            self._cached_tools.pop(server_id, None)
            logger.info(f"[MCPManager] 成功移除 MCP 服务: {server_id}")
            return True
        return False

    def toggle_server(self, server_id: str, enabled: bool) -> bool:
        """启用或禁用 MCP 服务"""
        if server_id in self._servers:
            self._servers[server_id]["enabled"] = enabled
            self.save_servers()
            return True
        return False

    async def probe_server_tools(self, server_id: str) -> List[Dict[str, Any]]:
        """
        通过 stdio 实时连接 MCP 服务子进程，调用 tools/list 协议握手探测该服务提供的全部工具
        """
        if server_id not in self._servers:
            return []

        s = self._servers[server_id]
        if not s.get("enabled", True):
            return []

        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client

            server_params = StdioServerParameters(
                command=s.get("command", "python3"),
                args=s.get("args", []),
                env={**os.environ, **(s.get("env") or {})},
            )

            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools_result = await session.list_tools()
                    tools = []
                    for t in tools_result.tools:
                        tools.append({
                            "name": t.name,
                            "description": t.description or "MCP 外部生态工具",
                            "input_schema": t.inputSchema if hasattr(t, "inputSchema") else {},
                            "server_id": server_id,
                        })
                    self._cached_tools[server_id] = tools
                    logger.info(f"[MCPManager] 服务 {server_id} 成功探测到 {len(tools)} 个 MCP 工具")
                    return tools
        except Exception as e:
            logger.warning(f"[MCPManager] 探测 MCP 服务 {server_id} 失败: {e}")
            return []

    async def execute_tool(self, server_id: str, tool_name: str, arguments: Dict[str, Any]) -> str:
        """
        连接 MCP 服务端进程并执行指定工具
        """
        if server_id not in self._servers:
            return f"错误：未找到 ID 为 '{server_id}' 的 MCP 服务"

        s = self._servers[server_id]
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client

            server_params = StdioServerParameters(
                command=s.get("command", "python3"),
                args=s.get("args", []),
                env={**os.environ, **(s.get("env") or {})},
            )

            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, arguments=arguments)
                    text_parts = []
                    if hasattr(result, "content") and result.content:
                        for item in result.content:
                            if hasattr(item, "text"):
                                text_parts.append(item.text)
                            else:
                                text_parts.append(str(item))
                    return "\n".join(text_parts) if text_parts else "MCP 工具执行完毕，未返回文本结果。"
        except Exception as e:
            logger.error(f"[MCPManager] 执行 MCP 工具 {tool_name} 失败: {e}", exc_info=True)
            return f"MCP 工具执行失败: {str(e)}"

    def get_langchain_tools(self) -> List[BaseTool]:
        """
        将当前所有已启用的 MCP 服务及其工具转换为 LangChain BaseTool 工具列表
        """
        lc_tools: List[BaseTool] = []
        for server_id, server_info in self._servers.items():
            if not server_info.get("enabled", True):
                continue
            cached = self._cached_tools.get(server_id, [])
            for t in cached:
                tool_name = f"mcp_{server_id}_{t['name']}"
                desc = f"[MCP生态工具 - 来自 {server_info['name']}] {t.get('description', '')}"
                lc_tools.append(
                    MCPToolWrapper(
                        name=tool_name,
                        description=desc,
                        server_id=server_id,
                        mcp_tool_name=t["name"],
                        raw_schema=t.get("input_schema", {}),
                    )
                )
        return lc_tools
