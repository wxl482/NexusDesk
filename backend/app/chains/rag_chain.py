from typing import List, Optional
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain_core.documents import Document

from app.rag.vector_engine import RAGEngine
from app.llm.factory import LLMFactory

# 1. 定义标准 LangChain Prompt 模板
RAG_SYSTEM_PROMPT = """你是一个严谨的专业知识问答助手。
请结合以下提供的参考文档片段回答用户的问题。
如果你在参考片段中找不到答案，请诚实说明，严禁凭空捏造。
回答时请条理分明，并列出引用的文档来源。

【参考文档片段】:
{context}
"""

rag_prompt = ChatPromptTemplate.from_messages([
    ("system", RAG_SYSTEM_PROMPT),
    ("human", "{question}"),
])

def format_docs(docs: List[Document]) -> str:
    """
    LangChain 标准格式化函数：将检索出的 Document 列表转换为带有来源标注的上下文文本，支持内容去重。
    """
    if not docs:
        return "（本地知识库未检索到相关片段）"

    formatted = []
    seen = set()
    idx = 1
    for doc in docs:
        content = doc.page_content.strip()
        h = hash(content)
        if h in seen:
            continue
        seen.add(h)
        source = doc.metadata.get("title", "未知来源")
        formatted.append(f"[{idx}] 文档: 《{source}》\n{content}\n")
        idx += 1
    return "\n".join(formatted)


def create_lcel_rag_chain(
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    temperature: float = 0.2,
    top_k: int = 4,
):
    """
    构建基于 LangChain 表达式语言 (LCEL: LangChain Expression Language) 的标准 RAG 检索问答链。
    
    经典 LCEL 流水线拓扑:
        question -> Retriever -> format_docs -> context \
                 -> RunnablePassthrough()    -> question / -> ChatPromptTemplate -> LLM -> StrOutputParser
    """
    # 实例化大模型
    llm = LLMFactory.get_chat_model(
        model=model,
        base_url=base_url,
        api_key=api_key,
        temperature=temperature,
        streaming=True,
    )

    # 获取 LangChain 标准检索器
    retriever = RAGEngine.get_instance().get_retriever(top_k=top_k)

    # 编排标准的 LangChain LCEL 链式管道
    rag_chain = (
        {
            "context": retriever | format_docs,
            "question": RunnablePassthrough(),
        }
        | rag_prompt
        | llm
        | StrOutputParser()
    )

    return rag_chain
