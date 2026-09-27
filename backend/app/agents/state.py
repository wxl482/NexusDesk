from typing import Annotated, Sequence, TypedDict, Optional, List, Dict, Any
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    """
    LangGraph 智能体状态图核心状态定义 (AgentState)。
    
    字段说明:
        messages: 完整的对话消息列表，通过 add_messages 实现增量追加、按 ID 更新或通过 RemoveMessage 移除压缩。
        summary: 滚动压缩的历史前序对话摘要文本。
        mode: 智能体运行模式（'chat' 极速对话, 'react' 自主推理与工具调用, 'multi_agent' 多智能体调度, 'rag' 知识库问答）。
        active_agent: 当前正在执行推理的活跃智能体角色标识。
        plan: 针对复杂长链路任务拆解生成的子任务步骤规划列表。
        extra_data: 供节点间传递自定义元数据的字典容器。
    """
    messages: Annotated[Sequence[BaseMessage], add_messages]
    summary: Optional[str]
    mode: str
    active_agent: Optional[str]
    plan: Optional[List[str]]
    extra_data: Optional[Dict[str, Any]]
    approval_mode: Optional[str]
    laya_decision: Optional[Dict[str, Any]]
    tool_steps: Optional[int]
