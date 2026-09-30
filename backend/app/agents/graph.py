import re
import uuid
import json
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# 导入 LangChain 核心提示词与消息模型
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import BaseMessage, SystemMessage, AIMessage, HumanMessage
from langchain_core.runnables import RunnablePassthrough

# 导入 LangGraph 状态图与内置组件
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.memory import MemorySaver

from app.agents.state import AgentState
from app.agents.compression import (
    default_compression_config,
    should_trigger_compression,
    compress_history_messages,
)
from app.tools.base import DEFAULT_TOOLS, get_all_tools
from app.llm.factory import LLMFactory
from app.agents.laya_service import laya_service
from app.agents.planner import generate_task_plan, should_decompose_goal
from app.agents.history_sanitizer import sanitize_message_history
from app.rag.knowledge_catalog import get_knowledge_base_prompt_context

# 全局共享内存检查点（Checkpointer），用于支持多轮连续对话上下文存储
memory_checkpointer = MemorySaver()

# 定义不同模式下的 LangChain ChatPromptTemplate
AGENT_PROMPT_TEMPLATE = ChatPromptTemplate.from_messages([
    ("system", "{system_prompt}"),
    MessagesPlaceholder(variable_name="messages"),
])

# 通用回复规范：杜绝机械复读与无意义客套
COMMON_OUTPUT_RULES = (
    "\n\n【回答规范与行为准则】\n"
    "1. 严禁复读提问：绝不可在回答开头或任何段落标题中机械重复、回显用户的提问或指令（例如用户输入“分析一下”、“总结一下”、“这是什么”，绝不要在开头输出“分析一下”、“总结一下”或将其作为标题）；\n"
    "2. 直入正题：开门见山，直接输出专业、严谨、排版美观的高质量分析结论或回答，杜绝“好的”、“没问题”、“下面为您分析”等无意义填充语；\n"
    "3. 排版美观：合理使用 Markdown 小标题、要点列表、代码块与关键加粗组织内容。"
)

# 系统核心提示词设定
SYSTEM_PROMPTS = {
    "chat": (
        "你是一个博学、友好且高效的中文 AI 智能助手。"
        "请清晰、条理分明地回答用户的问题，并使用排版良好的 Markdown 格式输出。"
        + COMMON_OUTPUT_RULES
    ),
    "react": (
        "你是一个具备高级自主规划与执行能力的全能智能体 (Autonomous Agent)，已配备强大的本地系统与专业技能工具箱。\n"
        "你具备以下核心操作能力：\n"
        "1. Model Context Protocol (MCP) 外部专业生态工具（以 `mcp_` 为前缀，如 SQLite 数据库查询 `mcp_sqlite_list_tables` / `mcp_sqlite_read_query` / `mcp_sqlite_describe_table`、网页抓取 `mcp_fetch_fetch` 等）；\n"
        "2. 系统终端命令执行 (`execute_terminal_command`)：可以在系统终端中运行 Shell 命令，如查看目录、运行 Git、执行构建、测试代码或环境状态探测；\n"
        "3. 本地文件全功能操作 (`read_local_file` / `write_local_file` / `list_local_directory` / `delete_local_file`)：可以直接阅读、创建、覆写或管理本地文件与工程目录；\n"
        "4. 实时互联网搜索 (`web_search`)、高精度 Python 计算 (`execute_python_code`) 以及私有知识库智能检索 (`query_knowledge_base`)。\n\n"
        "执行原则：\n"
        "1. 自主意图识别：如果是日常对话、逻辑推理或通用知识问答，直接给出排版良好的高质量回复，无需调用多余工具；\n"
        "2. 【MCP 专业工具最高优先级】：当用户请求查询本地数据库/SQL 数据（如查表结构、检索数据记录等）、或抓取外部专业网页时，【必须优先调用对应的专门 MCP 工具】（例如 `mcp_sqlite_list_tables` 查看表名，`mcp_sqlite_read_query` 执行 SELECT 查询），【严禁舍近求远】在终端运行 raw bash 命令（如 find 找 .db 文件、cat 查看、或用 python 临时写脚本连数据库）！\n"
        "3. 【知识库第一优先级】：当提问涉及任何技术概念、系统架构、产品功能、学习资料或已收录的参考文档时，必须优先主动调用 `query_knowledge_base` 在本地知识库中精准检索真实依据，严禁舍近求远去公网检索！\n"
        "4. 当需要运行通用系统命令、读写文件或检索最新时效信息时，自主精准调用对应工具并综合结果向用户提供清晰解答；\n"
        "5. 工具调用效率：进行网络检索等外部操作时，务必保持高效与克制。单次任务通常进行 1~2 次核心关键词检索即可充分掌握信息，严禁发起大量连续同质化检索造成严重网络延迟。"
        + COMMON_OUTPUT_RULES
    ),
    "rag": (
        "你是一位专精于私有知识库问答的专家助手。"
        "你的主要任务是利用 `query_knowledge_base` 工具检索本地知识库，并基于检索到的真实依据回答用户。"
        "严禁胡编乱造，回答时请明确标注引用的知识来源文档。"
        + COMMON_OUTPUT_RULES
    ),
    "multi_agent": (
        "你是多智能体协同架构的总调度官 (Multi-Agent Orchestrator)。\n"
        "你能够跨领域协调 MCP 外部生态工具 (如 SQLite 数据库查询、专用网页抓取)、系统终端运维 (Terminal Execution)、代码与文件工程师 (Local File Ops/Python)、网络调研员 (Search) 以及知识库专家的多重能力。\n"
        "遇到数据库查询需求时，直接调用对应的 MCP 工具 (如 mcp_sqlite_list_tables, mcp_sqlite_read_query)；遇到系统运维时谨慎调用终端工具。\n"
        "请自动将复杂的长链路任务拆解为清晰的执行子目标，充分利用工具链并在最终汇总一份高质量的交付成果。"
        + COMMON_OUTPUT_RULES
    ),
}

# 针对多智能体模式下由 Laya 毫秒级分流的具体子角色强化设定
SUB_AGENT_PROMPTS = {
    "coder": (
        "\n\n========================================\n"
        "【当前分派专项智能体：代码工程专家 (Coder Agent)】\n"
        "- 专长领域：系统架构设计、算法实现、代码编写、Bug 调试与性能重构。\n"
        "- 行为准则：直接交付规范、严谨、排版整洁并带有关键注释的代码方案。"
        "\n========================================"
    ),
    "researcher": (
        "\n\n========================================\n"
        "【当前分派专项智能体：网络研报与实时调研专家 (Researcher Agent)】\n"
        "- 专长领域：互联网全网检索、时效性资讯获取、外部官方文档核实。\n"
        "- 行为准则：主动调用 web_search 获取最新客观事实，并在结论中结构化标注文档依据。"
        "\n========================================"
    ),
    "terminal": (
        "\n\n========================================\n"
        "【当前分派专项智能体：系统终端运维专家 (Terminal Ops Agent)】\n"
        "- 专长领域：Shell 指令执行、本地文件与工程目录管理、环境依赖探测、Git 操作。\n"
        "- 行为准则：谨慎调用系统命令，遇到高危操作主动请求授权。"
        "\n========================================"
    ),
    "rag": (
        "\n\n========================================\n"
        "【当前分派专项智能体：私有知识库专家 (RAG Specialist)】\n"
        "- 专长领域：检索本地企业/私有知识库，基于真实文档回答问题。\n"
        "- 行为准则：主动调用 query_knowledge_base，杜绝凭空臆造。"
        "\n========================================"
    ),
    "chat": (
        "\n\n========================================\n"
        "【当前分派专项智能体：日常极速交互助手 (Chat Assistant)】\n"
        "- 专长领域：直接沟通、常识解释、创意生成、概念解答。\n"
        "- 行为准则：开门见山，无需调用多余工具，直接输出排版优美的 Markdown。"
        "\n========================================"
    ),
}


def parse_dsml_tool_calls(content: str) -> List[Dict[str, Any]]:
    """
    解析 DeepSeek 等模型原生吐出的 DSML (DeepSeek Markup Language) 标记，
    将其转化为标准 OpenAI / LangChain 格式的 tool_calls 字典。
    """
    invoke_pattern = re.compile(
        r'<[\|｜]?\s*DSML\s*[\|｜]{1,2}\s*invoke\s+name=[\"\'](?P<name>[^\"\']+)[\"\']\s*>(?P<body>.*?)</[\|｜]?\s*DSML\s*[\|｜]{1,2}\s*invoke>',
        re.DOTALL | re.IGNORECASE
    )
    param_pattern = re.compile(
        r'<[\|｜]?\s*DSML\s*[\|｜]{1,2}\s*parameter\s+name=[\"\'](?P<pname>[^\"\']+)[\"\'][^>]*>(?P<pval>.*?)</[\|｜]?\s*DSML\s*[\|｜]{1,2}\s*parameter>',
        re.DOTALL | re.IGNORECASE
    )

    tool_calls = []
    for inv in invoke_pattern.finditer(content):
        tool_name = inv.group('name')
        body = inv.group('body')
        args = {}
        for p in param_pattern.finditer(body):
            pname = p.group('pname')
            pval = p.group('pval').strip()
            if pval.lower() == 'true':
                pval = True
            elif pval.lower() == 'false':
                pval = False
            elif pval.isdigit():
                pval = int(pval)
            args[pname] = pval

        tool_calls.append({
            'name': tool_name,
            'args': args,
            'id': f'call_{uuid.uuid4().hex[:8]}',
            'type': 'tool_call'
        })
    return tool_calls


def clean_dsml_content(content: str) -> str:
    """
    净化包含 DSML 标签的文本正文，剔除原生 XML 结构，防止向用户前端流式泄露
    """
    cleaned = re.sub(
        r'<[\|｜]?\s*DSML\s*[\|｜]{1,2}\s*calls\s*>.*?</[\|｜]?\s*DSML\s*[\|｜]{1,2}\s*calls\s*>',
        '',
        content,
        flags=re.DOTALL | re.IGNORECASE
    )
    cleaned = re.sub(
        r'<[\|｜]?\s*DSML\s*[\|｜]{1,2}\s*invoke[\s\S]*?</[\|｜]?\s*DSML\s*[\|｜]{1,2}\s*invoke\s*>',
        '',
        cleaned,
        flags=re.DOTALL | re.IGNORECASE
    )
    cleaned = re.sub(r'</?[\|｜]?\s*DSML\s*[\|｜]{1,2}[^>]*>', '', cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def create_agent_graph(
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    temperature: Optional[float] = None,
):
    """
    构建并编译基于 LangChain + LangGraph 深度融合的状态图工作流 (StateGraph Workflow)。

    核心机制：
    1. 前端接入与会话状态由 LangChain AgentState 承载。
    2. 入口处挂接 compress_node 自动上下文压缩节点（多条件阈值检测与历史提炼）。
    3. 推理阶段基于 LangChain ChatPromptTemplate + MessagesPlaceholder 动态装配提示词。
    4. 工具绑定通过 LangChain ChatOpenAI.bind_tools(DEFAULT_TOOLS) 挂载。
    5. 执行链路基于 LangGraph StateGraph、ToolNode 与 tools_condition 闭环调度。
    """
    # 1. 实例化 LangChain 聊天模型与动态工具箱（融合原生系统工具与 MCP 外部生态工具）
    base_llm = LLMFactory.get_chat_model(
        model=model,
        base_url=base_url,
        api_key=api_key,
        temperature=temperature,
        streaming=True,
    )
    active_tools = get_all_tools()
    llm_with_tools = base_llm.bind_tools(active_tools)

    # 2. 基于 LangChain LCEL 构建推理链 (Prompt | LLM)
    chat_lcel_chain = AGENT_PROMPT_TEMPLATE | base_llm
    agent_lcel_chain = AGENT_PROMPT_TEMPLATE | llm_with_tools

    # 3. 上下文自动压缩前置节点 (Compress Node)
    async def compress_node(state: AgentState) -> Dict[str, Any]:
        raw_messages = state.get("messages", [])
        if not raw_messages:
            return {}

        messages, _ = sanitize_message_history(raw_messages)
        existing_summary = state.get("summary")
        model_name = getattr(base_llm, "model_name", None) or "default"

        if not should_trigger_compression(messages, existing_summary, default_compression_config, model_name=model_name):
            return {}

        # 压缩摘要时使用低温非流式模型调用，保证提炼结果严谨快速
        summary_llm = LLMFactory.get_chat_model(
            model=model,
            base_url=base_url,
            api_key=api_key,
            temperature=0.2,
            streaming=False,
        )

        removals, new_summary = await compress_history_messages(
            messages=messages,
            existing_summary=existing_summary,
            llm=summary_llm,
            messages_to_keep=default_compression_config.messages_to_keep,
        )

        if not removals:
            return {}

        return {
            "messages": removals,
            "summary": new_summary,
        }

    # 3.5 Laya System 1 毫秒级决策门禁节点 (Laya Gate Node)
    async def laya_gate_node(state: AgentState) -> Dict[str, Any]:
        """
        基于 Laya 的 System 1 决策前置节点 (推理耗时 ~30ms)。
        
        执行：
        1. 提取用户最新请求文本；
        2. 毫秒级意图识别、专项智能体分派与工具需求先验门禁；
        3. 将决策元数据写入状态，供后续节点与前端 SSE 流消费。
        """
        messages = state.get("messages", [])
        if not messages:
            return {}

        last_human_text = ""
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage) or getattr(msg, "type", "") in ["human", "user"]:
                if isinstance(msg.content, str):
                    last_human_text = msg.content
                elif isinstance(msg.content, list):
                    for part in msg.content:
                        if isinstance(part, dict) and part.get("type") == "text":
                            last_human_text += part.get("text", "") + " "
                break

        if not last_human_text.strip():
            return {}

        # 毫秒级决策 (CPU 单次前向 ~30ms)
        decision = laya_service.predict_intent_and_agent(last_human_text)
        active_agent = decision.get("agent", "coder")

        return {
            "active_agent": active_agent,
            "laya_decision": decision,
            "tool_steps": 0,  # 新会话轮次重置工具执行步数
        }

    # 3.8 长程任务规划状态机节点 (Planner Node)
    async def planner_node(state: AgentState) -> Dict[str, Any]:
        """
        长程任务规划状态机节点 (Plan-and-Solve)：
        针对复杂多步目标自动生成结构化执行规划清单，并注入状态图生命周期。
        """
        mode = state.get("mode", "react")
        if state.get("plan"):
            return {}

        messages = state.get("messages", [])
        last_human_text = ""
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage) or getattr(msg, "type", "") in ["human", "user"]:
                if isinstance(msg.content, str):
                    last_human_text = msg.content
                elif isinstance(msg.content, list):
                    for part in msg.content:
                        if isinstance(part, dict) and part.get("type") == "text":
                            last_human_text += part.get("text", "")
                break

        if not last_human_text.strip() or not should_decompose_goal(last_human_text, mode):
            return {}

        plan = await generate_task_plan(
            goal=last_human_text,
            model=model,
            base_url=base_url,
            api_key=api_key,
        )
        if plan and len(plan) > 0:
            plan[0]["status"] = "running"
            return {"plan": plan}
        return {}

    # 4. 核心智能体推理节点 (Agent Node)
    async def agent_node(state: AgentState) -> Dict[str, Any]:
        mode = state.get("mode", "react")
        prompt_text = SYSTEM_PROMPTS.get(mode, SYSTEM_PROMPTS["react"])
        summary = state.get("summary")

        # 若存在被自动压缩的历史摘要，作为背景信息无缝注入到系统提示词前置块中
        if summary:
            effective_system_prompt = (
                f"{prompt_text}\n\n"
                f"========================================\n"
                f"【前序历史对话要点摘要（已自动压缩归档）】\n"
                f"{summary}\n"
                f"========================================\n"
                f"请结合上述前序历史背景与下方最新消息继续为用户提供服务。"
            )
        else:
            effective_system_prompt = prompt_text

        # 多智能体模式下根据 Laya 毫秒级分流的 active_agent 动态强化系统提示词
        if mode == "multi_agent":
            current_agent = state.get("active_agent") or "coder"
            sub_prompt = SUB_AGENT_PROMPTS.get(current_agent, SUB_AGENT_PROMPTS["coder"])
            effective_system_prompt += sub_prompt

        # 若存在长程任务规划清单 (Plan-and-Solve)，将其结构化注入当前提示词中
        plan = state.get("plan")
        if plan and isinstance(plan, list):
            plan_lines = ["\n\n========================================", "【当前长程任务执行计划 (Plan-and-Solve)】"]
            for step in plan:
                status_icon = "⏳" if step.get("status") == "pending" else ("🔄" if step.get("status") == "running" else "✅")
                plan_lines.append(f"{status_icon} 步骤 {step.get('id')}: {step.get('title')} ({step.get('description', '')})")
            plan_lines.append("请围绕当前正在执行的步骤有序推进工具调用与分析！\n========================================")
            effective_system_prompt += "\n".join(plan_lines)

        # 结合当前操作批准权限策略注入安全规范
        approval_mode = state.get("approval_mode", "smart")
        
        # 核心基石准则：所有只读检索与计算工具 100% 直接执行，绝对严禁发起任何请求批准！
        BASE_SAFE_RULE = (
            "\n\n【核心权限原则与只读豁免】\n"
            "- 以下只读检索与计算工具属于 100% 安全操作，直接自主调用执行，绝对严禁向用户请求批准或输出 approval 代码块：\n"
            "  1. 互联网搜索 (`web_search`)：任何时候需要查阅最新网络资讯、官方新闻、技术文档，直接调用！绝不需要用户确认！\n"
            "  2. 读取本地文件 (`read_local_file`)：直接读取内容，绝不询问！\n"
            "  3. 浏览目录列表 (`list_local_directory`)：直接列举查看，绝不询问！\n"
            "  4. 私有知识库检索 (`query_knowledge_base`)：直接检索依据，绝不询问！\n"
            "  5. Python 数据计算 (`execute_python_code`)：直接运算求解，绝不询问！\n"
        )
        effective_system_prompt += BASE_SAFE_RULE

        if approval_mode == "ask_always":
            effective_system_prompt += (
                "\n========================================\n"
                "【操作权限规范：请求批准模式 (Ask Always)】\n"
                "- 当前用户启用了严格的「请求批准」策略。\n"
                "- 仅对写操作与系统命令请求批准：在写入/覆盖外部文件 (`write_local_file`)、删除文件 (`delete_local_file`)、或执行系统终端命令 (`execute_terminal_command`) 前，必须向用户请求批准。\n"
                "- （注：如前所述，网络搜索与文件读取依然直接执行，绝不询问！）\n"
                "- 请求批准时，简述操作理由，提示用户可直接点击下方操作卡片中的按钮完成决策，并在回复末尾附带如下标准的 approval 代码块：\n"
                "```approval\n"
                "{\n"
                '  "action": "execute_command",\n'
                '  "title": "允许我执行此终端命令吗？",\n'
                '  "type": "终端",\n'
                '  "target": "要执行的命令或目标路径",\n'
                '  "impact": "潜在影响说明",\n'
                '  "confirm_prompt": "允许执行：<目标>",\n'
                '  "reject_prompt": "已取消该操作，保留原状态。"\n'
                "}\n"
                "```\n"
                "- 【极重要执行准则】当收到授权执行指令（包含「允许执行」、「确认执行」）时，代表用户已同意，请立即自主调用工具执行真实操作！严禁在回复中输出任何“已确认”、“好的”、“收到”等客套开场白，直接调用工具并在完成后简短汇报真实结果！\n"
                "========================================"
            )
        elif approval_mode == "full_access":
            effective_system_prompt += (
                "\n========================================\n"
                "【操作权限与安全规范：完全访问权限模式 (Full Access)】\n"
                "- 用户已授予完全自主操作权限。\n"
                "- 可不受限制地访问互联网和电脑上的文件，自主调度所有工具高效达成任务目标，无需任何确认审批。\n"
                "========================================"
            )
        else: # smart (默认推荐)
            effective_system_prompt += (
                "\n========================================\n"
                "【操作权限与安全规范：帮我批准模式 (Smart Approval - 默认推荐)】\n"
                "- 常规开发操作（网络搜索、编写代码文件、浏览目录、查阅知识库、运行数据计算、常规只读终端命令如 git status 等）全部直接自主执行！\n"
                "- 仅对以下【高风险破坏性敏感操作】必须先向用户请求批准，严禁私自静默执行：\n"
                "  1. 永久删除本地文件 (`delete_local_file`)；\n"
                "  2. 破坏性或系统级危险终端指令（例如带有 rm、kill、mkfs、drop database 等破坏性命令）。\n"
                "- 请求批准时，简要说明待执行的操作与潜在影响，并在回复末尾附带如下标准的 approval 代码块（title 字段请使用亲切自然的疑问句，如：允许我在桌面创建名为“22”的文件夹吗？ 或 允许我永久删除该文件吗？）：\n"
                "```approval\n"
                "{\n"
                '  "action": "delete_file",\n'
                '  "title": "允许我永久删除该文件吗？",\n'
                '  "type": "文件系统",\n'
                '  "target": "待删除的文件完整路径或待执行命令",\n'
                '  "impact": "文件将被直接删除，不经过废纸篓，无法通过系统恢复。",\n'
                '  "confirm_prompt": "允许删除该文件：<目标路径>",\n'
                '  "reject_prompt": "已拒绝此操作，请取消删除，保留原有文件。"\n'
                "}\n"
                "```\n"
                "- 【极重要执行准则】当收到授权执行指令（包含「允许执行」、「确认执行」）时，代表用户已同意，请立即自主调用工具（如 `delete_local_file` 或 `execute_terminal_command`）执行真实操作！严禁在回复中输出任何“已确认”、“好的”、“收到”等客套开场白，直接调用工具并在完成后简短汇报真实结果！\n"
                "========================================"
            )

        raw_messages = list(state["messages"])
        messages, healed_replacements = sanitize_message_history(raw_messages)
        current_steps = state.get("tool_steps", 0) or 0

        # 提取用户最新提问文本，并动态注入本地私有知识库当前索引状态与就绪文档导引
        last_human_text = ""
        for msg in reversed(raw_messages):
            if isinstance(msg, HumanMessage) or getattr(msg, "type", "") in ["human", "user"]:
                if isinstance(msg.content, str):
                    last_human_text = msg.content
                elif isinstance(msg.content, list):
                    for part in msg.content:
                        if isinstance(part, dict) and part.get("type") == "text":
                            last_human_text += part.get("text", "") + " "
                break

        kb_prompt_block = get_knowledge_base_prompt_context(last_human_text)
        if kb_prompt_block:
            effective_system_prompt += kb_prompt_block

        # 在 react / multi_agent / rag 模式下，保持工具绑定能力，由 LLM 自主决定是否调用；
        # 仅当用户明确选择纯对话模式 (mode == 'chat') 或步数已达到收敛阈值 (>= 4) 时使用免工具的纯文本管道
        is_pure_chat = (mode == "chat")
        force_text_conclusion = is_pure_chat or (current_steps >= 4)

        if current_steps >= 3:
            effective_system_prompt += (
                "\n\n========================================\n"
                "【执行收敛提示】：当前任务已完成前序外部信息采集与工具执行。"
                "请综合已获得的全部信息，直接输出结构清晰、完整详实的最终中文分析与简报回答，绝对严禁再次发起任何工具调用或输出代码调用语法！\n"
                "========================================"
            )

        if force_text_conclusion:
            response = await chat_lcel_chain.ainvoke({
                "system_prompt": effective_system_prompt,
                "messages": messages,
            })
        else:
            response = await agent_lcel_chain.ainvoke({
                "system_prompt": effective_system_prompt,
                "messages": messages,
            })

        # 兼容与拦截 DeepSeek 原生 DSML (DeepSeek Markup Language) 标记泄露
        # 无论在多轮压缩后还是偶发格式异常，若模型直接吐出 <|DSML||calls> 文本，自动解析为真实的 tool_calls 执行，绝不向前端展示原始 XML 标记
        if isinstance(response.content, str) and ("DSML" in response.content):
            parsed_calls = parse_dsml_tool_calls(response.content)
            if parsed_calls:
                logger.info(f"[AgentNode] 成功拦截并解析 DeepSeek DSML 工具调用: {len(parsed_calls)} 个: {[c.get('name') for c in parsed_calls]}")
                if not hasattr(response, "tool_calls") or not response.tool_calls:
                    response.tool_calls = parsed_calls
                else:
                    response.tool_calls.extend(parsed_calls)
                response.content = clean_dsml_content(response.content)

        # 防御性校验：若已达最大步数，强制剥除可能残留的 tool_calls，确保输出纯文本并自然走向 END
        if current_steps >= 4 and getattr(response, "tool_calls", None):
            logger.info("[AgentNode] 已达到单轮最大工具调用步数 (4步)，强制剥离残留 tool_calls 以保障合规走向结束。")
            response.tool_calls = []
            if hasattr(response, "additional_kwargs"):
                response.additional_kwargs.pop("tool_calls", None)

        current_active = state.get("active_agent") or mode
        state_updates = [*healed_replacements, response]
        return {"messages": state_updates, "active_agent": current_active}

    # 5. 构造 LangGraph 状态图
    workflow = StateGraph(AgentState)

    # 包装 ToolNode 并记录步数，防止死循环
    base_tool_node = ToolNode(active_tools, handle_tool_errors=True)

    async def custom_tools_node(state: AgentState) -> Dict[str, Any]:
        """执行外部工具调用并递增计数器，带有全局容灾与 tool_call_id 防御闭环"""
        try:
            output = await base_tool_node.ainvoke(state)
        except Exception as e:
            logger.error(f"[ToolsNode] 工具节点执行异常: {e}", exc_info=True)
            # 找到触发此工具节点的最后一条 AIMessage，为其所有的 tool_call_id 生成容错 ToolMessage，确保状态闭环
            messages = state.get("messages", [])
            fallback_msgs = []
            if messages:
                last_msg = messages[-1]
                if isinstance(last_msg, AIMessage) and getattr(last_msg, "tool_calls", None):
                    for tc in last_msg.tool_calls:
                        cid = tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)
                        if cid:
                            from langchain_core.messages import ToolMessage
                            fallback_msgs.append(ToolMessage(
                                content=f"工具执行异常中断: {str(e)}",
                                tool_call_id=cid
                            ))
            output = {"messages": fallback_msgs}

        current_steps = (state.get("tool_steps", 0) or 0) + 1
        output["tool_steps"] = current_steps
        return output

    # 动态条件路由：检查是否有工具调用，且单轮工具调用上限严格限制为 4 轮
    def custom_tools_condition(state: AgentState) -> str:
        current_steps = state.get("tool_steps", 0) or 0
        if current_steps >= 4:
            return END
        return tools_condition(state)

    # 添加压缩前置节点、Laya 决策门禁节点、规划状态机节点、推理节点与工具节点
    workflow.add_node("compress_node", compress_node)
    workflow.add_node("laya_gate_node", laya_gate_node)
    workflow.add_node("planner_node", planner_node)
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", custom_tools_node)

    # 起始连接：START -> 压缩前置 -> Laya 决策门禁 -> 任务规划状态机 -> 核心 agent
    workflow.add_edge(START, "compress_node")
    workflow.add_edge("compress_node", "laya_gate_node")
    workflow.add_edge("laya_gate_node", "planner_node")
    workflow.add_edge("planner_node", "agent")

    # 动态条件路由
    workflow.add_conditional_edges(
        "agent",
        custom_tools_condition,
        {
            "tools": "tools",
            END: END,
        }
    )
    # 工具节点执行完毕后，回环连接回 agent 节点以进一步分析或完成答复
    workflow.add_edge("tools", "agent")

    # 挂载持久化检查点并编译
    app = workflow.compile(checkpointer=memory_checkpointer)
    return app
