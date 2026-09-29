import re
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from app.core.config import settings

logger = logging.getLogger(__name__)


def load_knowledge_snapshot() -> Dict[str, Any]:
    """
    轻量无锁读取本地知识库灾备快照（耗时 < 1ms，不占用 Milvus Lite 独占锁）
    """
    primary_file = settings.BACKUP_PATH / "knowledge_snapshot.json"
    redundant_file = settings.USER_BACKUP_PATH / "knowledge_snapshot.json"

    for fpath in [primary_file, redundant_file]:
        if fpath.exists():
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data and isinstance(data.get("documents"), dict):
                        return data
            except Exception as e:
                logger.warning(f"[KnowledgeCatalog] 读取快照文件 {fpath} 异常: {e}")
    return {"version": "1.0", "documents": {}}


def extract_keywords_from_title(title: str) -> List[str]:
    """从文档标题中提取具有辨识度的关键词与中英文 Token"""
    clean_title = re.sub(r"\.[a-zA-Z0-9]+$", "", title)
    # 提取英文/数字词组及 2 字及以上的连续汉字词
    tokens = re.findall(r"[a-zA-Z0-9]{2,}|[\u4e00-\u9fa5]{2,}", clean_title)
    # 过滤通用无辨识度词汇
    stopwords = {"文档", "文件", "资料", "未命名", "新建", "副本", "测试", "txt", "pdf", "docx"}
    return [t.lower() for t in tokens if t.lower() not in stopwords]


def check_knowledge_base_hit(query: str) -> Optional[List[str]]:
    """
    检测用户提问是否直接命中本地知识库中已上传的某篇或多篇文档。
    若命中，返回匹配的文档标题列表；否则返回 None。
    """
    if not query or not query.strip():
        return None

    snapshot = load_knowledge_snapshot()
    docs = snapshot.get("documents", {})
    if not docs:
        return None

    clean_query = query.lower()
    matched_titles: List[str] = []

    for doc_id, info in docs.items():
        title = info.get("title", "")
        if not title:
            continue
        tokens = extract_keywords_from_title(title)
        # 只要文档标题中的核心 token（例如 'langchain', '概述', '架构白皮书'）出现在 query 中
        if any(tok in clean_query for tok in tokens):
            matched_titles.append(title)

    return matched_titles if matched_titles else None


def get_knowledge_base_prompt_context(query: str = "") -> str:
    """
    生成注入给大模型 System Prompt 的【知识库就绪状态与动态导引清单】。
    
    效果：
    1. 让智能体清楚感知当前电脑里存了哪些私有参考资料（如《尚硅谷-01-LangChain概述.pdf》）；
    2. 确立“本地知识库优先”检索原则，杜绝舍近求远直接去公网搜索；
    3. 若当前提问精准命中某篇文档标题，输出高优先级的强命中行动提示。
    """
    snapshot = load_knowledge_snapshot()
    docs = snapshot.get("documents", {})
    if not docs:
        return ""

    doc_lines: List[str] = []
    matched_titles: List[str] = []
    clean_query = (query or "").lower()

    for doc_id, info in docs.items():
        title = info.get("title", "未命名文档")
        chunks = info.get("chunks_count", len(info.get("chunks", [])))
        doc_type = info.get("doc_type", "doc")
        category = info.get("category", "default")
        doc_lines.append(f"- 《{title}》 (共 {chunks} 个切片, 类型: {doc_type}, 分类: {category})")

        tokens = extract_keywords_from_title(title)
        if clean_query and any(tok in clean_query for tok in tokens):
            matched_titles.append(title)

    prompt_parts = [
        "\n\n========================================",
        f"【本地知识库当前已就绪索引清单 (共 {len(docs)} 篇)】",
        "当前系统本地私有知识库已建立多维语义切片与 BM25 倒排索引的资料：",
        *doc_lines,
        "\n【核心检索决策与知识库优先准则】：",
        "1. 【知识库第一优先级】：当用户的提问涉及上述已上传文档的主题、技术体系、原理概念或材料时，必须【首选】调用 `query_knowledge_base` 工具检索真实内容作为核心依据！",
        "2. 【严禁舍近求远】：如果本地知识库已有相关文档，绝对严禁直接调用 `web_search` 去公网搜索！必须优先以本地已收录的权威讲义与文档为准；",
        "3. 【公网搜索仅作兜底】：只有当调用 `query_knowledge_base` 确认未检索到相关内容，或用户明确提出“联网搜索最新全网新闻/时效资讯”时，才可使用 `web_search` 补充。",
    ]

    if matched_titles:
        hit_str = "、".join([f"《{t}》" for t in matched_titles])
        prompt_parts.append(
            f"\n🎯【精准命中提示】：用户当前提问与本地文档 [{hit_str}] 高度相关！请立即调用 `query_knowledge_base` 工具检索其内容并给出专业解答！"
        )

    prompt_parts.append("========================================\n")
    return "\n".join(prompt_parts)
