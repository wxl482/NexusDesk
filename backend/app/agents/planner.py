import json
import logging
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from app.llm.factory import LLMFactory

logger = logging.getLogger(__name__)


class PlanStep(BaseModel):
    id: int = Field(..., description="步骤编号，从 1 开始")
    title: str = Field(..., description="步骤简短标题")
    description: str = Field(default="", description="该步骤具体行动或目标说明")
    status: str = Field(default="pending", description="步骤状态: 'pending' | 'running' | 'completed' | 'failed'")
    result: Optional[str] = Field(default=None, description="执行成果摘要")


PLANNER_SYSTEM_PROMPT = """你是一个高阶长程任务架构师与规划专家。
你的任务是将用户的复杂或长链路目标拆解为 2 到 5 个高内聚、低耦合、按先后顺序执行的关键步骤。

【拆解原则】
1. 步骤精炼清晰：每个步骤有明确的输入、执行动作与预期产出；
2. 避免琐碎细化：切忌将单条终端命令或读单个文件拆成一个步骤，必须按宏观阶段拆解（例如：1. 环境与依赖探查，2. 核心模块开发，3. 自动化测试与验证）；
3. 必须输出合法 JSON 列表，格式如下，严禁包含任何多余解说文字：
```json
[
  {
    "id": 1,
    "title": "系统环境与依赖探测",
    "description": "探测项目结构、Git 状态与依赖环境是否满足运行条件"
  },
  {
    "id": 2,
    "title": "核心功能开发与改造",
    "description": "编写业务核心代码与配置"
  },
  {
    "id": 3,
    "title": "验证与交付测试",
    "description": "执行测试命令确保逻辑正确"
  }
]
```
"""


async def generate_task_plan(
    goal: str,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    针对用户的复杂需求自动生成结构化执行规划清单 (Plan-and-Solve)
    """
    try:
        llm = LLMFactory.get_chat_model(
            model=model,
            base_url=base_url,
            api_key=api_key,
            temperature=0.1,
            streaming=False,
        )
        messages = [
            SystemMessage(content=PLANNER_SYSTEM_PROMPT),
            HumanMessage(content=f"请为以下用户长程任务目标生成执行步骤清单：\n\n{goal}")
        ]
        response = await llm.ainvoke(messages)
        content = response.content if isinstance(response.content, str) else str(response.content)

        # 提取 JSON 块
        if "```json" in content:
            raw_json = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            raw_json = content.split("```")[1].split("```")[0].strip()
        else:
            raw_json = content.strip()

        parsed = json.loads(raw_json)
        if isinstance(parsed, list) and len(parsed) > 0:
            formatted_plan = []
            for i, item in enumerate(parsed, 1):
                formatted_plan.append({
                    "id": item.get("id", i),
                    "title": item.get("title", f"第 {i} 阶段任务"),
                    "description": item.get("description", ""),
                    "status": "pending",
                    "result": None,
                })
            return formatted_plan
    except Exception as e:
        logger.warning(f"[Planner] 动态生成计划失败，使用默认阶段降级: {e}")

    # 兜底通用三阶段规划
    return [
        {"id": 1, "title": "目标分析与信息检索", "description": "收集上下文与依赖事实", "status": "pending", "result": None},
        {"id": 2, "title": "方案实施与逻辑处理", "description": "调度专业技能完成主体工作", "status": "pending", "result": None},
        {"id": 3, "title": "成果整合与复核验证", "description": "验证结果并汇总高质量答复", "status": "pending", "result": None},
    ]


def should_decompose_goal(goal: str, mode: str = "react") -> bool:
    """
    判断当前用户需求是否适合触发长程任务规划拆解
    """
    if mode in ["multi_agent", "plan_solve"]:
        return True
    
    triggers = [
        "从头到尾", "完整实现", "规划一下", "制定计划", "开发一个", "重构",
        "长程任务", "步骤拆解", "调研并生成", "系统架构", "step by step", "plan"
    ]
    if len(goal) >= 15 and any(t in goal.lower() for t in triggers):
        return True

    return False
