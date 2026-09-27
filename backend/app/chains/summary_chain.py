from typing import Optional
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from app.llm.factory import LLMFactory

SUMMARY_SYSTEM_PROMPT = """你是一个专业高效的文本提炼与知识归纳专家。
请对给定的正文内容进行深度提炼，输出一份排版清晰的 Markdown 摘要报告：
1. 【核心主旨】：用 1-2 句话概括重点。
2. 【核心要点】：以项目符号列举 3-5 条关键信息。
3. 【关键结论或建议】：如有行动项或技术结论，在此列出。
"""

summary_prompt = ChatPromptTemplate.from_messages([
    ("system", SUMMARY_SYSTEM_PROMPT),
    ("human", "请对以下内容生成专业摘要：\n\n{text}"),
])

def create_summary_chain(
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    temperature: float = 0.3,
):
    """
    构建基于 LangChain LCEL 的文本深度摘要链。
    """
    llm = LLMFactory.get_chat_model(
        model=model,
        base_url=base_url,
        api_key=api_key,
        temperature=temperature,
        streaming=True,
    )

    # LCEL 流水线: summary_prompt | llm | StrOutputParser()
    chain = summary_prompt | llm | StrOutputParser()
    return chain
