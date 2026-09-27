import os
import subprocess
from pathlib import Path
from typing import Optional
from langchain_core.tools import tool
from app.core.config import BASE_DIR

@tool
def execute_terminal_command(command: str, cwd: Optional[str] = None, timeout: int = 60) -> str:
    """
    在本地操作系统终端中执行指定的 Shell / Bash 命令行，并实时捕获标准输出 (stdout)、标准错误 (stderr) 以及退出状态码。
    适用于查看目录或文件状态、运行 Git 命令、执行项目脚本、测试运行代码、安装第三方依赖或执行构建任务。

    参数:
        command: 要在终端中运行的有效命令行字符串（例如 'git status'、'ls -la'、'python3 tests/test_core.py' 等）
        cwd: 命令运行所在的工作目录（可选）。如不提供，默认在当前项目根目录下运行。
        timeout: 命令运行的最长超时秒数，默认 60 秒。
    """
    cmd_clean = command.strip()
    if not cmd_clean:
        return "命令执行失败：命令内容不能为空。"

    # 1. 前置 Laya 极速毫秒级破坏性安全审计拦截 (如 rm -rf, mkfs, dd 等)
    from app.agents.laya_service import laya_service
    risk_audit = laya_service.audit_action_risk("execute_terminal_command", cmd_clean)
    if risk_audit.get("is_high_risk") and risk_audit.get("risk_score", 0) >= 0.90:
        return (
            f"【安全门禁主动拦截】：系统已阻断执行高危破坏性系统指令！\n"
            f"拦截理由: {risk_audit.get('reason', '检测到高危破坏性特征')}\n"
            f"阻断命令: {cmd_clean}\n"
            f"系统已保护本地重要环境不受损坏。"
        )

    # 解析目标执行路径
    target_cwd = Path(cwd) if cwd else BASE_DIR
    if not target_cwd.is_absolute():
        target_cwd = (BASE_DIR / target_cwd).resolve()
    else:
        target_cwd = target_cwd.resolve()

    if not target_cwd.exists():
        return f"命令执行失败：目标工作目录 '{target_cwd}' 不存在。"

    # 预设防挂起与非交互式终端环境变量（防止 npm init, sudo 等交互式挂死进程）
    env = os.environ.copy()
    env["PAGER"] = "cat"
    env["TERM"] = "dumb"
    env["PYTHONUNBUFFERED"] = "1"
    env["CI"] = "true"
    env["DEBIAN_FRONTEND"] = "noninteractive"
    env["GIT_TERMINAL_PROMPT"] = "0"

    try:
        process = subprocess.run(
            command,
            shell=True,
            cwd=str(target_cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )

        stdout = process.stdout or ""
        stderr = process.stderr or ""
        returncode = process.returncode

        # 限制最大输出字符数，避免大输出撑爆 LLM 上下文 Token
        max_chars = 8000
        truncated_note = ""
        if len(stdout) > max_chars:
            stdout = stdout[:max_chars] + f"\n... [控制台输出较长，已截断显示前 {max_chars} 字符]"
        if len(stderr) > max_chars:
            stderr = stderr[:max_chars] + f"\n... [错误输出较长，已截断显示前 {max_chars} 字符]"

        if returncode == 0:
            output_body = stdout if stdout else "（命令已顺利执行完毕，无控制台标准输出）"
            return (
                f"【终端命令执行成功】\n"
                f"工作目录: {target_cwd}\n"
                f"退出状态码: 0\n\n"
                f"控制台输出:\n{output_body}"
            )
        else:
            return (
                f"【终端命令执行异常 (退出码 {returncode})】\n"
                f"工作目录: {target_cwd}\n\n"
                f"标准输出:\n{stdout if stdout else '（无）'}\n\n"
                f"标准错误:\n{stderr if stderr else '（无）'}"
            )

    except subprocess.TimeoutExpired:
        return f"终端命令执行超时：命令运行超过 {timeout} 秒未结束，已自动终止进程以保障系统响应。\n运行命令: {command}"
    except Exception as e:
        return f"调用本地终端发生严重异常: {str(e)}"
