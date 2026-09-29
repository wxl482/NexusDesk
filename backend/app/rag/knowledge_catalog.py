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
    两阶段动态感知与粗筛路由器 (Two-Stage Query-Time Knowledge Routing):
    彻底解决海量文档 (> 100~10,000 篇) 时的 Prompt 膨胀与上下文污染问题。

    扩展设计：
    1. 【常态紧凑折叠】：
       文档总数超过 5 篇时，绝对禁止向 Prompt 全量倾倒文档列表，仅输出宏观统计与分类摘要（< 30 Tokens）；
    2. 【提问前置动态粗筛 (Top-3~Top-5)】：
       根据当前提问对全部文档标题与关键词执行毫秒级倒排打分；仅当提问命中了相关文档时，才将最相关的 3~5 篇作为参考候选注入；
    3. 【无关问题零注入】：
       若用户提问的是常规闲聊、天气或无关任务，注入列表严格为 0，完全无 Token 浪费与干扰；
    4. 【总文档少量 (<= 5) 时自动透出】：
       对于本地仅有少量文档的场景，自动展示精简清单供模型清晰认知。
    """
    snapshot = load_knowledge_snapshot()
    docs = snapshot.get("documents", {})
    if not docs:
        return ""

    total_count = len(docs)
    categories: Dict[str, int] = {}
    for d in docs.values():
        cat = d.get("category", "default")
        categories[cat] = categories.get(cat, 0) + 1

    cat_items = [f"{k}({v}篇)" for k, v in list(categories.items())[:4]]
    cat_summary = ", ".join(cat_items) if cat_items else "通用(全部)"

    # 执行提问相关性粗筛打分 (Top-K 候选截断，最大限制 5 篇)
    clean_query = (query or "").lower().strip()
    matched_candidates: List[Dict[str, Any]] = []

    if clean_query:
        for doc_id, info in docs.items():
            title = info.get("title", "")
            tokens = extract_keywords_from_title(title)
            hits = [tok for tok in tokens if tok in clean_query]
            if hits:
                matched_candidates.append({
                    "title": title,
                    "hit_count": len(hits),
                    "chunks": info.get("chunks_count", len(info.get("chunks", []))),
                    "category": info.get("category", "default"),
                })

        # 按命中关键词匹配度倒序排序，严格截取最相关的 Top-5
        matched_candidates.sort(key=lambda x: x["hit_count"], reverse=True)
        matched_candidates = matched_candidates[:5]

    prompt_parts = [
        "\n\n========================================",
        f"【本地私有知识库状态】：已建立索引共 {total_count} 篇文档 (覆盖分类: {cat_summary})。",
        "【核心检索决策准则】：涉及专业知识、技术原理、业务规范或非时效性概念时，必须【优先调用 query_knowledge_base】检索本地文档事实，严禁直接去公网搜索 (web_search)；仅当本地未检索到或明确要求全网最新资讯时才用公网搜索。",
    ]

    # 场景 A: 提问命中了具体候选文档（展示 Top-K 候选）
    if matched_candidates:
        prompt_parts.append("\n🎯【与当前提问最相关的本地候选参考文档 (前置粗筛命中)】：")
        for cand in matched_candidates:
            prompt_parts.append(f"- 《{cand['title']}》 (共 {cand['chunks']} 个切片, 分类: {cand['category']})")
        prompt_parts.append("请【第一优先级】首先调用 `query_knowledge_base` 精准检索上述文档内容并回答！")

    # 场景 B: 提问未命中特定文档，但总文档数很少 (<= 5 篇) 时展示极简概览
    elif total_count <= 5:
        prompt_parts.append("\n【当前已收录参考文档概览】：")
        for doc_id, info in docs.items():
            prompt_parts.append(f"- 《{info.get('title', '未知')}》 (分类: {info.get('category', 'default')})")

    prompt_parts.append("========================================\n")
    return "\n".join(prompt_parts)
