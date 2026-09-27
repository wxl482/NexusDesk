import os
import shutil
from pathlib import Path
from typing import List, Optional
from langchain_core.tools import tool
from app.core.config import settings, BASE_DIR

def _resolve_target_path(path_str: str) -> Path:
    """
    统一解析路径：支持绝对路径，或相对于当前项目根目录 (BASE_DIR) 的相对路径。
    """
    p = Path(path_str)
    if not p.is_absolute():
        p = (BASE_DIR / p).resolve()
    else:
        p = p.resolve()
    return p

def _read_local_file_impl(file_path: str, max_chars: int = 50000) -> str:
    """内部读取文件实现函数，供各工具调用"""
    try:
        path = _resolve_target_path(file_path)
        if not path.exists():
            return f"读取失败：文件 '{file_path}' (解析路径: {path}) 不存在。"
        if not path.is_file():
            return f"读取失败：'{file_path}' 是一个目录而不是普通文件。如需查看目录内容，请调用 list_local_directory 工具。"

        file_size = path.stat().st_size
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read(max_chars)
        
        note = ""
        if file_size > len(content):
            note = f"\n\n[提示: 文件总大小 {file_size} 字节，已截取前 {len(content)} 字符输出]"

        return f"【文件内容读取成功 ({path})】\n\n{content}{note}"
    except Exception as e:
        return f"读取文件 '{file_path}' 发生异常: {str(e)}"

def _write_local_file_impl(file_path: str, content: str) -> str:
    """内部写入文件实现函数，供各工具调用"""
    try:
        path = _resolve_target_path(file_path)
        # 确保父级目录完整存在
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

        return f"【文件写入成功】\n文件路径: {path}\n写入字符数: {len(content)} 字符\n状态: 已成功同步至本地磁盘。"
    except Exception as e:
        return f"写入文件 '{file_path}' 发生异常: {str(e)}"

def _list_local_directory_impl(dir_path: str = ".", max_items: int = 50) -> str:
    """内部列举目录实现函数，供各工具调用"""
    try:
        target_dir = _resolve_target_path(dir_path)
        if not target_dir.exists():
            return f"目录浏览失败：目标目录 '{dir_path}' (解析路径: {target_dir}) 不存在。"
        if not target_dir.is_dir():
            return f"目录浏览失败：'{dir_path}' 是文件而非目录。请调用 read_local_file 查看文件内容。"

        # 常见海量噪声目录，避免占用上下文
        IGNORED_NAMES = {".git", "node_modules", "venv", ".venv", "__pycache__", ".DS_Store"}

        entries = []
        all_children = sorted(target_dir.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        
        count = 0
        skipped = 0
        for item in all_children:
            if item.name in IGNORED_NAMES and dir_path == ".":
                skipped += 1
                continue
            count += 1
            if count > max_items:
                break
            
            kind = "[目录]" if item.is_dir() else "[文件]"
            size_str = ""
            if item.is_file():
                size_str = f"({item.stat().st_size} 字节)"
            entries.append(f"{kind.ljust(6)} {item.name} {size_str}")

        if not entries:
            return f"目录 '{dir_path}' 为空。"

        result = [
            f"【目录浏览结果 ({target_dir})】",
            f"共展示 {len(entries)} 项条目" + (f" (已跳过常见系统/依赖目录)" if skipped > 0 else "") + ":",
            "",
            "\n".join(entries),
        ]
        if count > max_items:
            result.append(f"\n... 还有更多条目被省略（已达单次最大上限 {max_items} 条）。")

        return "\n".join(result)
    except Exception as e:
        return f"列举目录 '{dir_path}' 失败: {str(e)}"

def _delete_local_file_impl(file_path: str) -> str:
    """内部删除文件实现函数，包含沙箱保护与高危审计"""
    try:
        path = _resolve_target_path(file_path)
        if not path.exists():
            return f"删除失败：文件 '{file_path}' 不存在。"
        if path.is_dir():
            return f"删除安全保护拦截：'{file_path}' 是一个目录。本工具仅用于删除普通文件。"

        # 核心系统关键路径与用户主目录防御拦截
        home = Path.home().resolve()
        system_roots = {Path("/").resolve(), Path("/System").resolve(), Path("/Library").resolve(), Path("/usr").resolve(), Path("/bin").resolve(), Path("/sbin").resolve(), Path("/etc").resolve(), Path("/var").resolve()}

        if path == BASE_DIR or path.parent == path or path == home or path in system_roots:
            return "【安全门禁拦截】：禁止删除操作系统核心根目录、核心工程根目录或用户主目录！"

        for sys_dir in system_roots:
            if sys_dir != Path("/").resolve() and sys_dir in path.parents:
                return f"【安全门禁拦截】：目标文件位于系统受保护目录 '{sys_dir}' 下，已被底层安全网自动防御阻断。"

        # Laya 毫秒级安全模型风险评估
        from app.agents.laya_service import laya_service
        audit = laya_service.audit_action_risk("delete_local_file", str(path))
        if audit.get("is_high_risk") and audit.get("risk_score", 0) >= 0.90:
            return f"【安全门禁拦截】：Laya 安全模型识别到极高破坏风险 ({audit.get('reason', '高危敏感文件')})，已自动阻断删除。"

        path.unlink()
        return f"成功删除本地文件: {path}"
    except Exception as e:
        return f"删除文件 '{file_path}' 发生异常: {str(e)}"

@tool
def read_local_file(file_path: str, max_chars: int = 50000) -> str:
    """
    读取本地文件系统中的文件内容（支持代码文件、文本、配置文件、日志等）。
    支持项目相对路径（例如 'package.json'、'backend/main.py'、'frontend/src/App.vue'）或系统绝对路径。

    参数:
        file_path: 目标文件路径（相对项目根目录或绝对路径）
        max_chars: 最大读取字符数限制（默认 50000 字符），防止过大文件撑爆模型上下文
    """
    return _read_local_file_impl(file_path, max_chars)

@tool
def write_local_file(file_path: str, content: str) -> str:
    """
    在本地文件系统中创建新文件或覆写已有文件内容。
    如果目标文件的上级父目录尚不存在，系统会自动递归创建对应文件夹。

    参数:
        file_path: 目标文件路径（相对项目根目录或绝对路径）
        content: 要写入的文本内容字符串
    """
    return _write_local_file_impl(file_path, content)

@tool
def list_local_directory(dir_path: str = ".", max_items: int = 50) -> str:
    """
    浏览和列举本地目录结构与文件清单，帮助了解工程文件分布与目录组织。
    支持自动过滤 node_modules、.git、venv 等常见海量非必要目录。

    参数:
        dir_path: 待浏览的目标目录路径（默认 '.' 代表当前项目根目录）
        max_items: 最多展示的子文件/文件夹条目数，默认 50 条
    """
    return _list_local_directory_impl(dir_path, max_items)

@tool
def delete_local_file(file_path: str) -> str:
    """
    删除本地指定的文件（安全保护：不支持删除非空目录，不支持删除系统根目录）。

    参数:
        file_path: 待删除的文件相对路径或绝对路径
    """
    return _delete_local_file_impl(file_path)

# 保持兼容原有的沙箱工作区快捷工具别名
@tool
def read_workspace_file(file_path: str) -> str:
    """读取本地工作区文件内容（向下兼容快捷工具）。"""
    return _read_local_file_impl(file_path)

@tool
def write_workspace_file(file_path: str, content: str) -> str:
    """向本地工作区写入或创建文件（向下兼容快捷工具）。"""
    return _write_local_file_impl(file_path, content)

@tool
def list_workspace_files(subdir: str = "") -> str:
    """列举本地工作区目录文件列表（向下兼容快捷工具）。"""
    return _list_local_directory_impl(subdir if subdir else ".")
