import sys
import io
import traceback
from typing import Dict, Any
from langchain_core.tools import tool

@tool
def execute_python_code(code: str) -> str:
    """
    在交互式 Python 沙箱环境中执行给定的 Python 代码，并实时捕获标准输出 (stdout)、标准错误 (stderr) 以及表达式返回值。
    非常适用于数学计算、复杂算法模拟、数据清洗与变换、统计分析等场景。
    提示：在代码中请尽量使用 print(...) 打印关键变量，以便直接观察输出。

    参数:
        code: 待执行的有效 Python 代码字符串
    """
    # 暂存原有标准输出和错误流，重定向到内存 buffer
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    redirected_output = io.StringIO()
    redirected_error = io.StringIO()

    sys.stdout = redirected_output
    sys.stderr = redirected_error

    # 构建安全环境上下文
    safe_globals: Dict[str, Any] = {
        "__builtins__": __builtins__,
    }
    local_vars: Dict[str, Any] = {}

    try:
        # 首先尝试将代码作为表达式进行求值 (eval)
        try:
            compiled = compile(code, "<agent_exec>", "eval")
            res = eval(compiled, safe_globals, local_vars)
            output = redirected_output.getvalue()
            error = redirected_error.getvalue()
            if output:
                return f"标准输出:\n{output}\n求值结果: {res}"
            return f"求值结果: {res}"
        except SyntaxError:
            # 若不是纯表达式，则作为完整代码块执行 (exec)
            compiled = compile(code, "<agent_exec>", "exec")
            exec(compiled, safe_globals, local_vars)
            output = redirected_output.getvalue()
            error = redirected_error.getvalue()
            res_str = ""
            if output:
                res_str += f"标准输出:\n{output}\n"
            if error:
                res_str += f"标准错误:\n{error}\n"
            if not res_str:
                res_str = "代码执行成功，无标准控制台输出。"
            return res_str
    except Exception:
        err = traceback.format_exc()
        return f"沙箱执行异常:\n{err}"
    finally:
        # 无论成功还是异常，必须还原系统的标准流
        sys.stdout = old_stdout
        sys.stderr = old_stderr
