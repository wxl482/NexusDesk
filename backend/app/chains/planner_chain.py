from typing import List, Optional
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from app.llm.factory import LLMFactory

class SubTask(BaseModel):
    """分解生成的单步子任务定义"""
    step_id: int = Field(description="步骤序号")
    description: str = Field(description="子任务执行描述")
    assigned_role: str = Field(description="指定执行该任务的角色：'researcher' | 'coder' | 'rag_expert' | 'analyst'")
    suggested_tool: str = Field(description="建议调用的工具名称，如 'web_search', 'execute_python_code' 等")

class TaskPlan(BaseModel):
    """
    智能体高层任务规划 Pydantic 结构化输出模型
    """
    user_intent: str = Field(description="对用户真实核心诉求的高度归纳")
    complexity_level: str = Field(description="任务复杂度评估：'simple' | 'medium' | 'complex'")
    steps: List[SubTask] = Field(description="拆解后的步骤列表")


def create_planner_chain(
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
):
    """
    构建基于 LangChain JsonOutputParser 与 Pydantic Schema 的任务规划分解链 (Planner Chain)。
    """
    # 构造 LangChain JsonOutputParser
    parser = JsonOutputParser(pydantic_object=TaskPlan)

    # 构造带格式指令注入的 ChatPromptTemplate
    planner_prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            "你是一个资深多智能体任务规划师 (Task Planner)。\n"
            "请分析用户的原始需求，将其深度拆解为逻辑严密、可执行的子任务清单。\n"
            "{format_instructions}\n"
            "必须严格按照 JSON 规范输出，不得添加任何前置或后置废话。"
        ),
        ("human", "请拆解并规划以下任务：\n{task}"),
    ]).partial(format_instructions=parser.get_format_instructions())

    # 实例化大模型
    llm = LLMFactory.get_chat_model(
        model=model,
        base_url=base_url,
        api_key=api_key,
        temperature=0.1,
        streaming=False,
    )

    # LCEL 链式组装: Prompt -> LLM -> JsonOutputParser
    planner_chain = planner_prompt | llm | parser
    return planner_chain
