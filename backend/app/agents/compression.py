"""
上下文自动压缩与多策略治理模块 (Context Compression Engine)

功能职责:
1. 提供多维度的上下文压缩触发策略定义 (条数 messages, 上下文占比 fraction, 绝对 Token 数 tokens);
2. 预设当前用于测试的极低触发门槛 (trigger_message_count = 6);
3. 预留模型物理最大上下文百分比阈值 (trigger_context_fraction = 0.7);
4. 安全地将待压缩历史与需保留的最新消息解耦，严格保护 ToolCall / ToolMessage 闭环对齐;
5. 基于结构化 Prompt 调用 LLM 生成滚动上下文提炼摘要，更新图状态并剔除冗余历史。
"""

import logging
from dataclasses import dataclass
from typing import List, Tuple, Optional, Literal, Sequence, Dict, Any

from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    AIMessage,
    ToolMessage,
    SystemMessage,
    RemoveMessage,
)
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.language_models import BaseChatModel

logger = logging.getLogger(__name__)

# 常见主流大模型的最大上下文 Token 上限参考表 (可根据实际选型动态匹配)
MODEL_CONTEXT_LIMITS: Dict[str, int] = {
    "deepseek-chat": 1000000,       # DeepSeek 最新 1M (100万 Token) 超大上下文窗口
    "deepseek-reasoner": 1000000,   # DeepSeek R1 深度思考 1M 超大上下文
    "gpt-4o": 128000,
    "gpt-4o-mini": 128000,
    "qwen-plus": 128000,
    "qwen-max": 128000,
    "moonshot-v1-8k": 8000,
    "moonshot-v1-32k": 32000,
    "moonshot-v1-128k": 128000,
    "glm-4-flash": 128000,
    "llama3.2": 8000,
    "default": 128000,
}

@dataclass
class CompressionConfig:
    """
    上下文自动压缩触发与保留策略配置 (针对常规 OA 办公与文档处理优化)
    """
    # 触发策略模式:
    # - "any": 任意条件满足即触发 (复合策略，生产与OA办公首选推荐：超轮次或超Token即压缩)
    # - "messages": 仅按消息条数触发
    # - "fraction": 仅按模型最大输入上下文的百分比阈值触发
    # - "tokens": 仅按绝对 Token 数量阈值触发
    strategy: Literal["any", "messages", "fraction", "tokens"] = "any"

    # 1. 消息条数触发阈值: 18 条 (约 9 轮完整问答，保障多次修改打磨草稿时不被打断)
    trigger_message_count: int = 18

    # 2. 绝对 Token 触发阈值: 32,000 Tokens (贴入长制度、长合同时防止上下文暴涨拖慢响应)
    trigger_token_threshold: int = 32000

    # 3. 模型最大上下文百分比阈值: 0.60 (60%)
    trigger_context_fraction: float = 0.60

    # 4. 压缩触发后，保留在活跃上下文中的最近消息条数 (保留最近 8 条消息，即约 4 轮完整问答与草稿细节)
    messages_to_keep: int = 8


# 全局默认压缩策略单例
default_compression_config = CompressionConfig()


# 专业的会话历史滚动摘要 Prompt 模板 (特别强化 OA 办公与文档处理的关键数据与条款留存)
CONVERSATION_SUMMARY_PROMPT = """你是一个专业的长对话上下文精炼与记忆管理专家。
以下是智能体与用户的前序历史对话记录。因为上下文长度即将达到上限，你需要提取其中所有最具价值的核心信息，生成一份排版清晰、结构紧凑的 Markdown 摘要。
此摘要将替换被压缩的历史对话，供智能体在后续多轮交互中继续准确理解上下文背景。特别是在文档处理与办公任务中，请务必准确保留关键数据与结论。

请严格按照以下四项结构化清单进行提炼（如无对应项写“无”）：
1. 【会话核心目标】：用户本次会话的核心诉求、要处理的主题文档或主要任务是什么？
2. 【关键结论与定稿数据】：双方达成了什么重要共识？确认了哪些关键条款、具体金额、日期、人员或定稿意见？（务必保留确切数字与事实，切勿过度概括）
3. 【涉及的文件与产物】：创建、修改、引用或查看了哪些文档、文件路径、代码或数据产物？
4. 【当前最新进度与待办】：任务进行到了哪一步？接下来准备做什么或正在等待什么？

{existing_summary_clause}

待压缩的前序历史对话记录：
{dialogue_text}

请直接输出精炼后的 Markdown 摘要，不要包含任何客套或无关说明。"""


def estimate_tokens_approx(text: str) -> int:
    """
    轻量快速的 Token 粗估函数（无需额外外部依赖）：
    中文通常 1.5 字符约 1 Token，英文/代码约 3.5~4 字符约 1 Token。
    """
    if not text:
        return 0
    # 统计中文字符数
    cjk_count = sum(1 for ch in text if '\u4e00' <= ch <= '\u9fff')
    other_count = len(text) - cjk_count
    estimated = int(cjk_count * 0.75 + other_count * 0.25)
    return max(1, estimated)


def estimate_messages_tokens(messages: Sequence[BaseMessage]) -> int:
    """计算消息列表中所有消息正文与工具调用的总估算 Token 数量"""
    total = 0
    for m in messages:
        if isinstance(m.content, str):
            content = m.content
        elif isinstance(m.content, list):
            # 多模态复合结构：提取纯文本部分并估算图片固定开销
            text_parts = []
            img_count = 0
            for part in m.content:
                if isinstance(part, dict):
                    if part.get("type") == "text":
                        text_parts.append(part.get("text", ""))
                    elif part.get("type") == "image_url":
                        img_count += 1
            content = " ".join(text_parts)
            total += img_count * 500  # 预估每张图片约消耗 500 Tokens
        else:
            content = str(m.content)

        total += estimate_tokens_approx(content)
        if hasattr(m, "tool_calls") and m.tool_calls:
            total += estimate_tokens_approx(str(m.tool_calls))
    return total


def should_trigger_compression(
    messages: Sequence[BaseMessage],
    existing_summary: Optional[str] = None,
    config: Optional[CompressionConfig] = None,
    model_name: Optional[str] = None,
) -> bool:
    """
    根据配置策略判断当前会话是否已达到上下文压缩阈值。
    """
    cfg = config or default_compression_config
    if not messages:
        return False

    current_tokens = estimate_messages_tokens(messages)
    if existing_summary:
        current_tokens += estimate_tokens_approx(existing_summary)

    target_model = (model_name or "").lower()
    max_tokens = MODEL_CONTEXT_LIMITS.get(target_model, MODEL_CONTEXT_LIMITS["default"])

    msg_exceeded = len(messages) >= cfg.trigger_message_count
    tokens_exceeded = current_tokens >= cfg.trigger_token_threshold
    fraction_exceeded = (current_tokens / max_tokens) >= cfg.trigger_context_fraction

    # 1. 复合策略 (推荐生产模式): 任意条件满足即触发
    if cfg.strategy == "any":
        return msg_exceeded or tokens_exceeded or fraction_exceeded

    # 2. 单一策略模式
    elif cfg.strategy == "messages":
        return msg_exceeded
    elif cfg.strategy == "tokens":
        return tokens_exceeded
    elif cfg.strategy == "fraction":
        return fraction_exceeded

    return False


def split_messages_for_compression(
    messages: Sequence[BaseMessage],
    messages_to_keep: int = 8,
) -> Tuple[List[BaseMessage], List[BaseMessage]]:
    """
    安全拆分待压缩消息与保留消息：
    保证保留消息（to_keep）的起始点是一个独立的 HumanMessage，
    严禁将处于同一轮内的 AIMessage(tool_calls) 与 ToolMessage 拆散。
    """
    if len(messages) <= messages_to_keep:
        return [], list(messages)

    cutoff = max(1, len(messages) - messages_to_keep)

    # 向前（更早的方向）寻找最近的一个 HumanMessage 作为保留序列的完整起点
    while cutoff > 0:
        msg = messages[cutoff]
        if isinstance(msg, HumanMessage) or getattr(msg, "type", "") == "human":
            break
        cutoff -= 1

    to_compress = list(messages[:cutoff])
    to_keep = list(messages[cutoff:])
    return to_compress, to_keep


def format_dialogue_text(messages: Sequence[BaseMessage]) -> str:
    """将消息列表格式化为易于大模型阅读提炼的清晰文本"""
    lines = []
    for m in messages:
        role = "用户" if isinstance(m, HumanMessage) else "智能助手" if isinstance(m, AIMessage) else "工具执行"
        if isinstance(m.content, str):
            content = m.content
        elif isinstance(m.content, list):
            text_parts = []
            has_image = False
            for part in m.content:
                if isinstance(part, dict):
                    if part.get("type") == "text":
                        text_parts.append(part.get("text", ""))
                    elif part.get("type") == "image_url":
                        has_image = True
            content = " ".join(text_parts)
            if has_image:
                content += " [用户附带上传了图片]"
        else:
            content = str(m.content)

        if hasattr(m, "tool_calls") and m.tool_calls:
            tool_names = [tc.get("name", "") for tc in m.tool_calls]
            lines.append(f"[{role}]: (调用工具: {', '.join(tool_names)}) {content}")
        else:
            lines.append(f"[{role}]: {content}")
    return "\n\n".join(lines)


async def compress_history_messages(
    messages: Sequence[BaseMessage],
    existing_summary: Optional[str],
    llm: BaseChatModel,
    messages_to_keep: int = 8,
) -> Tuple[List[RemoveMessage], str]:
    """
    执行实际的消息提炼与剔除：
    1. 拆分早期消息与保留消息；
    2. 将早期消息（结合已有前序摘要）送入大模型生成全新融合摘要；
    3. 生成针对被压缩消息的 RemoveMessage 列表，供 LangGraph 执行状态瘦身。
    """
    to_compress, to_keep = split_messages_for_compression(messages, messages_to_keep)
    if not to_compress:
        return [], existing_summary or ""

    dialogue_text = format_dialogue_text(to_compress)

    if existing_summary:
        existing_clause = (
            "【注意】：此前已经生成过一份前序摘要。请务必将【既有摘要内容】与【本次新增的历史对话】"
            f"有机融合成一份完整、不重复的最新精炼摘要：\n\n【既有前序摘要】：\n{existing_summary}\n"
        )
    else:
        existing_clause = "这是首次执行历史提炼，请完整归纳以下对话重点。"

    # 构造 LCEL 摘要链
    prompt = ChatPromptTemplate.from_template(CONVERSATION_SUMMARY_PROMPT)
    chain = prompt | llm | StrOutputParser()

    try:
        new_summary = await chain.ainvoke({
            "existing_summary_clause": existing_clause,
            "dialogue_text": dialogue_text,
        })
    except Exception as e:
        logger.error(f"执行上下文自动压缩摘要生成失败: {e}", exc_info=True)
        # 若大模型摘要异常，返回旧摘要并不剔除消息，保证对话安全
        return [], existing_summary or ""

    # 生成待剔除的消息 ID 清单 (通过 LangGraph 的 RemoveMessage)
    removals = [RemoveMessage(id=m.id) for m in to_compress if getattr(m, "id", None)]

    return removals, new_summary.strip()
