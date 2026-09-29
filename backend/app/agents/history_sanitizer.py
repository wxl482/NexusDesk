import logging
from typing import List, Tuple, Sequence, Optional, Dict, Any
from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    AIMessage,
    ToolMessage,
    SystemMessage,
)

logger = logging.getLogger(__name__)


def sanitize_message_history(
    messages: Sequence[BaseMessage]
) -> Tuple[List[BaseMessage], List[BaseMessage]]:
    """
    深度自愈与消息流校验器 (Message History Sanitizer & Auto-Healer)。
    严格对齐 OpenAI / Anthropic / Qwen / DeepSeek 官方 Tool Calling 消息协议规范。

    核心自愈能力：
    1. 【未闭合 ToolCall 自愈】：
       当 AIMessage 声明了 tool_calls，但后续因为用户提前发问、异常中断、网络断开或单轮步数上限，
       导致没有紧随对应的 ToolMessage 时：
       - 若后续紧跟 HumanMessage 且完全没有工具响应：将该 AIMessage 的 tool_calls 与 additional_kwargs["tool_calls"] 清空，
         转换为纯文本助手回复，防止触发 400 校验异常；
       - 若后续已有部分 ToolMessage，但遗漏了某个 tool_call_id：自动为缺失的 ID 补齐防御性 ToolMessage(content="[该操作已跳过或取消]", tool_call_id=missing_id)。
    2. 【孤立 ToolMessage 清理】：
       若 ToolMessage 前面没有声明该 tool_call_id 的对应 AIMessage，坚决剔除，防止 OpenAI 报错 "Tool message must follow an assistant message with tool calls"。
    3. 【尾部悬挂 ToolCall 防御】：
       若消息历史末尾是一条带有 tool_calls 的 AIMessage（例如上轮中断残留），自动清除其 tool_calls。
    4. 【返回参数】：
       返回 (sanitized_messages_for_llm, healed_replacements_for_state)
       - sanitized_messages_for_llm: 100% 合规的消息序列，直接供 llm.ainvoke / lcel 使用；
       - healed_replacements_for_state: 需要在 LangGraph state 检查点中被替换/更新的修复消息列表（利用 add_messages 的按 id 原地替换机制）。
    """
    if not messages:
        return [], []

    sanitized: List[BaseMessage] = []
    healed_replacements: List[BaseMessage] = []
    i = 0
    n = len(messages)

    while i < n:
        msg = messages[i]

        # 1. 检查是否为带有 tool_calls 的 AIMessage
        has_tool_calls = bool(getattr(msg, "tool_calls", None))
        raw_kwargs_tc = getattr(msg, "additional_kwargs", {}).get("tool_calls", [])
        if isinstance(msg, AIMessage) and (has_tool_calls or bool(raw_kwargs_tc)):
            tool_calls = getattr(msg, "tool_calls", []) or []
            declared_call_ids: List[str] = []
            for tc in tool_calls:
                cid = tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)
                if cid and cid not in declared_call_ids:
                    declared_call_ids.append(cid)
            for tc in raw_kwargs_tc:
                cid = tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)
                if cid and cid not in declared_call_ids:
                    declared_call_ids.append(cid)

            # 收集其后紧跟的所有连续 ToolMessage
            subsequent_tool_msgs: List[ToolMessage] = []
            answered_call_ids = set()
            j = i + 1
            while j < n and isinstance(messages[j], ToolMessage):
                t_msg = messages[j]
                t_id = getattr(t_msg, "tool_call_id", None)
                if t_id and t_id in declared_call_ids:
                    subsequent_tool_msgs.append(t_msg)
                    answered_call_ids.add(t_id)
                j += 1

            # 场景 A: 没有任何匹配的 ToolMessage 紧随其后 (例如用户直接发送了新消息或已是末尾)
            if not subsequent_tool_msgs:
                content = msg.content if isinstance(msg.content, str) else ""
                if not content.strip():
                    content = "[已完成前序指令分析，已收敛前序操作]"
                cleaned_kwargs = {
                    k: v for k, v in getattr(msg, "additional_kwargs", {}).items() if k != "tool_calls"
                }
                cleaned_ai = AIMessage(
                    content=content,
                    id=getattr(msg, "id", None),
                    additional_kwargs=cleaned_kwargs,
                    tool_calls=[],
                )
                sanitized.append(cleaned_ai)
                if getattr(msg, "id", None):
                    healed_replacements.append(cleaned_ai)
                logger.info(f"[HistorySanitizer] 成功自愈未闭合的悬挂 AIMessage(id={getattr(msg, 'id', None)})，已清除未完成的 tool_calls。")
                i += 1
                continue

            # 场景 B: 有部分 ToolMessage，但存在未被响应的 tool_call_id
            missing_ids = [cid for cid in declared_call_ids if cid not in answered_call_ids]
            sanitized.append(msg)
            sanitized.extend(subsequent_tool_msgs)

            # 为缺失的 tool_call_id 在其后补齐合成的防御性 ToolMessage
            for missing_id in missing_ids:
                synth_tool_msg = ToolMessage(
                    content="[该操作执行超时或已由会话切换取消]",
                    tool_call_id=missing_id,
                )
                sanitized.append(synth_tool_msg)
                healed_replacements.append(synth_tool_msg)
                logger.info(f"[HistorySanitizer] 成功补全缺失的防御性 ToolMessage(tool_call_id={missing_id})。")

            i = j
            continue

        # 2. 检查是否为孤立的 ToolMessage (前面没有合法的 AIMessage tool_calls 对应)
        elif isinstance(msg, ToolMessage):
            logger.warning(f"[HistorySanitizer] 剔除孤立的 ToolMessage(id={getattr(msg, 'id', None)}, tool_call_id={getattr(msg, 'tool_call_id', None)})")
            i += 1
            continue

        # 3. 其他常规消息 (HumanMessage, SystemMessage, 普通 AIMessage)
        else:
            sanitized.append(msg)
            i += 1

    return sanitized, healed_replacements
