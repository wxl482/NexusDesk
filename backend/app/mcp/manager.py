import os
import sys
import json
import shutil
import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Type
from pydantic import BaseModel, Field, create_model

from langchain_core.tools import BaseTool
from app.core.config import settings

logger = logging.getLogger(__name__)


def create_model_from_json_schema(model_name: str, schema: Dict[str, Any]) -> Optional[Type[BaseModel]]:
    """
    将标准 MCP 工具的 JSON Schema 动态编译为 Pydantic BaseModel。
    确保 LangChain / ChatOpenAI bind_tools 时能准确向大模型暴露工具参数定义。
    """
    if not isinstance(schema, dict):
        return None
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))
    fields: Dict[str, Any] = {}
    type_map = {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
        "array": list,
        "object": dict,
    }
    for field_name, field_info in properties.items():
        if not isinstance(field_info, dict):
            continue
        field_type = type_map.get(field_info.get("type", "string"), Any)
        field_desc = field_info.get("description", "")
        if field_name in required:
            fields[field_name] = (field_type, Field(description=field_desc))
        else:
            default_val = field_info.get("default", None)
            fields[field_name] = (Optional[field_type], Field(default=default_val, description=field_desc))

    try:
        return create_model(model_name, **fields)
    except Exception as e:
        logger.warning(f"[MCPManager] 动态构建工具模型 {model_name} 失败: {e}")
        return None


def resolve_command_and_env(command: str, custom_env: Optional[Dict[str, str]] = None) -> Tuple[str, Dict[str, str]]:
    """
    智能解析 MCP 子进程启动命令与环境变量。
    优先定向到当前虚拟环境 bin 目录，自动补齐 macOS / Linux 核心 PATH。
    """
    env = {**os.environ, **(custom_env or {})}
    venv_bin = os.path.dirname(sys.executable)
    extra_paths = [venv_bin, "/opt/homebrew/bin", "/usr/local/bin"]
    existing_path = env.get("PATH", "")
    paths_to_add = [p for p in extra_paths if p and p not in existing_path.split(os.pathsep)]
    if paths_to_add:
        env["PATH"] = os.pathsep.join(paths_to_add) + os.pathsep + existing_path

    # 若命令为 python 或 python3，直接锁定为当前虚拟环境的解释器
    if command in ["python", "python3"]:
        return sys.executable, env

    # 优先在当前 venv_bin 中寻找可执行脚本 (如 mcp-server-sqlite)
    direct_venv_path = os.path.join(venv_bin, command)
    if os.path.isfile(direct_venv_path) and os.access(direct_venv_path, os.X_OK):
        return direct_venv_path, env

    # 查全局系统 PATH
    resolved_cmd = shutil.which(command, path=env.get("PATH"))
    return resolved_cmd or command, env


def resolve_args(args: List[str]) -> List[str]:
    """
    智能解析命令行参数中的相对路径（如 --db-path ./backend/data/app.db），转换为系统绝对路径
    """
    resolved = []
    for arg in args:
        if isinstance(arg, str) and (arg.startswith("./") or arg.startswith("../")):
            p = Path(arg).resolve()
            if p.exists():
                resolved.append(str(p))
                continue
            backend_p = (Path("backend") / arg.lstrip("./")).resolve()
            if backend_p.exists():
                resolved.append(str(backend_p))
                continue
            if arg.startswith("./backend/"):
                stripped_p = Path(arg.replace("./backend/", "./")).resolve()
                if stripped_p.exists():
                    resolved.append(str(stripped_p.resolve()))
                    continue
        resolved.append(arg)
    return resolved


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
        schema = raw_schema or {}
        # 动态编译 schema 注入 args_schema，使大模型明确获知此工具入参属性与字段释义
        clean_model_name = f"{server_id}_{mcp_tool_name}_Input".replace("-", "_").replace(".", "_")
        dynamic_model = create_model_from_json_schema(clean_model_name, schema)
        super().__init__(
            name=name,
            description=description,
            server_id=server_id,
            mcp_tool_name=mcp_tool_name,
            raw_schema=schema,
            args_schema=dynamic_model,
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
        """从 JSON 配置文件中读取 MCP 客户端服务配置与工具缓存"""
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._servers = data.get("servers", {})
                    # 恢复持久化的工具定义缓存，确保服务重启后立即可用
                    for s_id, s_info in self._servers.items():
                        if "tools" in s_info and isinstance(s_info["tools"], list):
                            self._cached_tools[s_id] = s_info["tools"]
            except Exception as e:
                logger.warning(f"[MCPManager] 加载配置文件失败: {e}")
                self._servers = {}
        else:
            # 预设几个开箱即用官方驱动
            self._servers = {
                "sqlite": {
                    "id": "sqlite",
                    "name": "SQLite Database Query",
                    "transport": "stdio",
                    "command": "mcp-server-sqlite",
                    "args": ["--db-path", "./data/app.db"],
                    "enabled": True,
                    "description": "通过标准 SQL 查询本地 SQLite 数据库表结构与数据记录",
                },
                "fetch": {
                    "id": "fetch",
                    "name": "Web Content Fetcher (官方 MCP)",
                    "transport": "stdio",
                    "command": "mcp-server-fetch",
                    "args": [],
                    "enabled": True,
                    "description": "基于官方 MCP 规范的外部网页内容与 Markdown 提取服务",
                },
            }
            self.save_servers()

    def save_servers(self):
        """将配置持久化至磁盘（包含工具定义缓存）"""
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump({"servers": self._servers}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"[MCPManager] 保存 MCP 配置失败: {e}")

    def list_servers(self) -> List[Dict[str, Any]]:
        """获取所有已注册的 MCP 服务列表及状态，附加已缓存的工具列表与数量"""
        res = []
        for s_id, s_info in self._servers.items():
            item = dict(s_info)
            cached = self._cached_tools.get(s_id, [])
            item["tools"] = cached
            item["tools_count"] = len(cached)
            res.append(item)
        return res

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
        # 保留已有的工具缓存
        if server_id in self._servers and "tools" in self._servers[server_id]:
            server_info["tools"] = self._servers[server_id]["tools"]
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
        通过 stdio 实时连接 MCP 服务子进程，调用 tools/list 协议握手探测该服务提供的全部工具，
        探测成功后自动持久化到本地 JSON 配置文件。
        """
        if server_id not in self._servers:
            return []

        s = self._servers[server_id]
        if not s.get("enabled", True):
            return []

        cmd, env = resolve_command_and_env(s.get("command", "python3"), s.get("env"))
        args = resolve_args(s.get("args", []))

        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client

            server_params = StdioServerParameters(
                command=cmd,
                args=args,
                env=env,
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
                    self._servers[server_id]["tools"] = tools
                    self.save_servers()
                    logger.info(f"[MCPManager] 服务 {server_id} 成功探测到 {len(tools)} 个 MCP 工具并已持久化缓存")
                    return tools
        except Exception as e:
            logger.warning(f"[MCPManager] 探测 MCP 服务 {server_id} 失败: {e}")
            return []

    async def auto_probe_all_enabled(self):
        """服务启动或配置变更时，后台并发自动探测所有已启用的 MCP 服务工具"""
        tasks = []
        for s_id, s_info in self._servers.items():
            if s_info.get("enabled", True):
                tasks.append(self.probe_server_tools(s_id))
        if tasks:
            logger.info(f"[MCPManager] 开始自动探测 {len(tasks)} 个已启用 MCP 服务的工具箱...")
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for s_id, res in zip([s for s, i in self._servers.items() if i.get("enabled", True)], results):
                if isinstance(res, Exception):
                    logger.warning(f"[MCPManager] 自动探测 MCP 服务 {s_id} 异常: {res}")
                else:
                    logger.info(f"[MCPManager] MCP 服务 {s_id} 探测就绪，包含 {len(res)} 个可用工具")

    async def execute_tool(self, server_id: str, tool_name: str, arguments: Dict[str, Any]) -> str:
        """
        连接 MCP 服务端进程并执行指定工具
        """
        if server_id not in self._servers:
            return f"错误：未找到 ID 为 '{server_id}' 的 MCP 服务"

        s = self._servers[server_id]
        cmd, env = resolve_command_and_env(s.get("command", "python3"), s.get("env"))
        args = resolve_args(s.get("args", []))

        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client

            server_params = StdioServerParameters(
                command=cmd,
                args=args,
                env=env,
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
