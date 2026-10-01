import os
import sys
import platform
import datetime
from pathlib import Path
from typing import Dict, Any, List
from fastapi import APIRouter, Response
from app.core.config import settings, LOG_DIR

router = APIRouter(tags=["服务健康检查与系统诊断"])


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


def _get_recent_logs(max_lines: int = 80) -> List[str]:
    """读取当天或最新的日志文件末尾若干行"""
    try:
        log_files = sorted(LOG_DIR.glob("app_*.log"), key=lambda f: f.stat().st_mtime, reverse=True)
        if not log_files:
            return ["[系统日志目录无历史日志文件]"]
        latest_file = log_files[0]
        with open(latest_file, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
            return [line.rstrip() for line in lines[-max_lines:]]
    except Exception as e:
        return [f"[读取日志发生异常: {str(e)}]"]


def _collect_diagnostics_data() -> Dict[str, Any]:
    """汇总采集完整的系统诊断数据快照"""
    # 检查 Postgres 检查点池状态
    try:
        from app.agents.graph import _pg_pool
        pg_status = "connected" if _pg_pool is not None else "memory_fallback"
    except Exception:
        pg_status = "unknown"

    # 检查 RAG 向量库与切片数量
    try:
        from app.rag.vector_engine import RAGEngine
        engine = RAGEngine.get_instance()
        docs = engine.list_documents()
        rag_info = {
            "status": "ready",
            "backend": "milvus_or_chroma",
            "document_count": len(docs),
        }
    except Exception as e:
        rag_info = {
            "status": "error",
            "message": str(e),
            "document_count": 0,
        }

    # 检查 MCP 插件状态
    try:
        from app.mcp.manager import MCPManager
        mcp_mgr = MCPManager.get_instance()
        servers = mcp_mgr.list_servers()
        enabled_count = sum(1 for s in servers if s.get("enabled", False))
        mcp_info = {
            "total_servers": len(servers),
            "enabled_servers": enabled_count,
            "servers": [
                {
                    "id": s.get("id"),
                    "name": s.get("name"),
                    "enabled": s.get("enabled", False),
                    "command": s.get("command"),
                }
                for s in servers
            ]
        }
    except Exception as e:
        mcp_info = {
            "status": "error",
            "message": str(e),
            "total_servers": 0,
            "enabled_servers": 0,
            "servers": []
        }

    # 汇总诊断字典
    return {
        "timestamp": datetime.datetime.now().isoformat(),
        "app": {
            "name": settings.APP_NAME,
            "version": settings.VERSION,
            "debug": settings.DEBUG,
            "pid": os.getpid(),
        },
        "system": {
            "os": platform.system(),
            "os_release": platform.release(),
            "architecture": platform.machine(),
            "python_version": sys.version.split(" ")[0],
            "python_path": sys.executable,
        },
        "storage_and_services": {
            "checkpointer": pg_status,
            "rag": rag_info,
            "mcp": mcp_info,
            "default_provider": settings.DEFAULT_PROVIDER,
            "default_model": settings.DEFAULT_MODEL,
            "default_base_url": settings.DEFAULT_BASE_URL,
            "has_api_key": bool(settings.DEFAULT_API_KEY.strip()),
        },
        "recent_logs": _get_recent_logs(80)
    }


@router.get("/api/system/diagnostics")
async def get_system_diagnostics():
    """
    获取完整系统健康与运行环境诊断数据，用于前端设置面板快速检测与问题排查。
    """
    return _collect_diagnostics_data()


@router.get("/api/system/diagnostics/export")
async def export_system_diagnostics():
    """
    导出系统诊断报告（JSON 文件下载），包含环境信息、各子模块健康状态及最新后端日志。
    """
    import json
    data = _collect_diagnostics_data()
    json_bytes = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
    now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"nexusdesk_diagnostics_{now_str}.json"

    return Response(
        content=json_bytes,
        media_type="application/json",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "Access-Control-Expose-Headers": "Content-Disposition",
        }
    )
