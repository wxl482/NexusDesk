import sys
from pathlib import Path

# 将 backend 根目录置入 sys.path，支持独立脚本执行
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.tools.python_exec import execute_python_code
from app.tools.terminal import execute_terminal_command
from app.tools.file_ops import (
    write_workspace_file,
    read_workspace_file,
    list_workspace_files,
    read_local_file,
    write_local_file,
    list_local_directory,
)
from app.rag.vector_engine import RAGEngine
from app.chains.rag_chain import create_lcel_rag_chain, rag_prompt
from app.chains.planner_chain import create_planner_chain
from app.agents.graph import create_agent_graph

def test_tools():
    """测试核心扩展工具链（终端执行、本地文件 IO、Python 计算）"""
    print("[测试 1/4] 开始验证 LangChain 工具链 (终端执行、本地文件与计算引擎)...")
    
    # 1. 验证终端命令执行
    term_res = execute_terminal_command.invoke({"command": "echo 'Terminal execution test OK'"})
    print("终端执行输出:", term_res)
    assert "Terminal execution test OK" in term_res, "终端命令执行验证失败"

    # 2. 验证 Python 计算沙箱
    res = execute_python_code.invoke({"code": "x = [i**2 for i in range(5)]; print(x)"})
    print("计算引擎输出:", res)
    assert "[0, 1, 4, 9, 16]" in res, "Python 代码执行验证失败"

    # 3. 验证本地文件全功能操作
    w_local = write_local_file.invoke({"file_path": "data/test_local.txt", "content": "Local file operations work!"})
    print("本地文件写入:", w_local)
    r_local = read_local_file.invoke({"file_path": "data/test_local.txt"})
    print("本地文件读取:", r_local)
    assert "Local file operations work!" in r_local, "本地文件读写验证失败"

    l_local = list_local_directory.invoke({"dir_path": "data"})
    print("本地目录浏览:", l_local)
    assert "test_local.txt" in l_local, "本地目录列举验证失败"


def test_rag():
    """测试基于 LangChain Document 与 Chroma 的 RAG 向量知识库"""
    print("[测试 2/4] 开始验证 LangChain Chroma 知识库引擎...")
    engine = RAGEngine.get_instance()
    upload_res = engine.add_text_document(
        title="LangChain 全家桶架构指南",
        text="LangChain 是主流的 LLM 编排框架，包含 Prompt、Chains (LCEL)、Memory、Tools 与 LangGraph 状态图全套组件。",
    )
    print("文档入库响应:", upload_res)
    assert upload_res["success"] is True

    search_res = engine.search_similar("LangChain 全家桶包含哪些组件？", top_k=2)
    print("检索结果条数:", len(search_res))
    assert len(search_res) > 0
    print("最相关段落:", search_res[0]["content"])

def test_lcel_chains():
    """测试 LangChain LCEL 表达式语言链与 PromptTemplate 管道构造"""
    print("[测试 3/4] 开始验证 LangChain LCEL 链式管道与 PromptTemplate...")
    # 验证 Prompt 模板格式化
    formatted_prompt = rag_prompt.format_messages(
        context="[1] 示例文档: LangChain",
        question="什么是 LangChain？",
    )
    assert len(formatted_prompt) == 2
    assert "什么是 LangChain？" in formatted_prompt[1].content
    print("Prompt 格式化成功: ", formatted_prompt[0].content[:30], "...")

    # 验证 LCEL RAG 链与 Planner 链能否正常实例化
    rag_chain = create_lcel_rag_chain()
    planner_chain = create_planner_chain()
    assert rag_chain is not None
    assert planner_chain is not None
    print("LCEL RAG 链与 Planner 规划链构造成功！")

def test_agent_graph():
    """测试 LangChain 与 LangGraph 状态图编译"""
    print("[测试 4/4] 开始验证 LangChain + LangGraph StateGraph 编译...")
    graph = create_agent_graph()
    assert graph is not None
    print("LangGraph 状态图编译就绪！")

if __name__ == "__main__":
    test_tools()
    test_rag()
    test_lcel_chains()
    test_agent_graph()
    print("\n✅ LangChain 全套组件（Prompts, LCEL Chains, Chroma, Tools, LangGraph）验证全部通过！")
