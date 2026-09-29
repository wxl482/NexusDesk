import math
import re
from typing import List, Dict, Any, Optional, Tuple
import jieba
from rank_bm25 import BM25Plus
from langchain_core.documents import Document

from app.core.logger import logger


class ChineseBM25Retriever:
    """
    基于 jieba 中文精准分词 + BM25Plus 的稀疏关键词检索器。
    采用 BM25Plus 算法杜绝常规 BM25 在小样本或高频词时的 IDF 归零与负分问题，
    专门解决稠密向量检索在专有名词、代码变量、精细型号匹配失真的问题。
    """
    def __init__(self):
        self.corpus_chunks: List[Dict[str, Any]] = []
        self.bm25: Optional[BM25Plus] = None
        self.tokenized_corpus: List[List[str]] = []

    def tokenize(self, text: str) -> List[str]:
        """中文分词与英文单词提取"""
        text = text.lower()
        # 英文连续单词/型号/数字保留
        words = list(jieba.cut_for_search(text))
        return [w.strip() for w in words if len(w.strip()) > 0]

    def build_index(self, chunks: List[Dict[str, Any]]):
        """构建/更新 BM25 内存倒排索引"""
        self.corpus_chunks = chunks
        if not chunks:
            self.bm25 = None
            self.tokenized_corpus = []
            return

        self.tokenized_corpus = [
            self.tokenize(c.get("page_content", ""))
            for c in chunks
        ]
        self.bm25 = BM25Plus(self.tokenized_corpus)
        logger.info(f"[BM25] 成功构建关键词索引，语料切片数: {len(chunks)}")

    def search(self, query: str, top_k: int = 10, category: Optional[str] = None) -> List[Tuple[Dict[str, Any], float]]:
        """执行 BM25 检索，返回排序后的 (chunk, bm25_score) 列表，支持按分类过滤"""
        if not self.bm25 or not self.corpus_chunks:
            return []

        tokens = self.tokenize(query)
        if not tokens:
            return []

        scores = self.bm25.get_scores(tokens)
        scored_pairs = []
        for i, score in enumerate(scores):
            if score > 0.0001:
                chunk = self.corpus_chunks[i]
                if category:
                    chunk_cat = chunk.get("metadata", {}).get("category", "default")
                    if chunk_cat != category:
                        continue
                scored_pairs.append((chunk, float(score)))

        scored_pairs.sort(key=lambda x: x[1], reverse=True)
        return scored_pairs[:top_k]


class HybridRAGFusion:
    """
    【P0 工业级混合检索与重排序融合器】
    整合 Milvus 稠密向量检索 + BM25 稀疏检索，并采用 RRF (Reciprocal Rank Fusion) 倒数排名融合算法。
    """
    def __init__(self, rrf_k: int = 60):
        self.rrf_k = rrf_k

    def fuse(
        self,
        dense_results: List[Dict[str, Any]],
        sparse_results: List[Tuple[Dict[str, Any], float]],
        top_k: int = 4
    ) -> List[Dict[str, Any]]:
        """
        利用 RRF 倒数排名融合算法融合多路召回结果：
        RRF_Score = 1 / (K + rank_dense) + 1 / (K + rank_sparse)
        """
        scores: Dict[str, float] = {}
        chunk_map: Dict[str, Dict[str, Any]] = {}

        # 1. 计入稠密向量检索排名得分
        for rank, item in enumerate(dense_results, 1):
            key = f"{item.get('doc_id', '')}_{item.get('chunk_index', 0)}"
            if not item.get("doc_id"):
                key = str(hash(item.get("content", "")))
            chunk_map[key] = item
            scores[key] = scores.get(key, 0.0) + (1.0 / (self.rrf_k + rank))

        # 2. 计入稀疏 BM25 关键词检索排名得分
        for rank, (item, bm25_score) in enumerate(sparse_results, 1):
            meta = item.get("metadata", {})
            key = f"{meta.get('doc_id', '')}_{meta.get('chunk_index', 0)}"
            if not meta.get("doc_id"):
                key = str(hash(item.get("page_content", "")))
            if key not in chunk_map:
                chunk_map[key] = {
                    "content": item.get("page_content", ""),
                    "title": meta.get("title", "未知来源"),
                    "doc_id": meta.get("doc_id", ""),
                    "category": meta.get("category", "default"),
                    "chunk_index": meta.get("chunk_index", 0),
                    "parent_content": meta.get("parent_content"),
                    "distance": 1.0,
                    "bm25_score": round(bm25_score, 4),
                }
            else:
                chunk_map[key]["bm25_score"] = round(bm25_score, 4)
            scores[key] = scores.get(key, 0.0) + (1.0 / (self.rrf_k + rank))

        # 3. 按最终混合融合评分从高到低排序
        sorted_keys = sorted(scores.keys(), key=lambda k: scores[k], reverse=True)
        final_results = []
        for k in sorted_keys[:top_k]:
            res = dict(chunk_map[k])
            res["rrf_score"] = round(scores[k], 5)
            # 如果存在父切片 (Parent Chunking)，自动填充父切片内容以提供更完整上下文
            if res.get("parent_content"):
                res["content"] = res["parent_content"]
            final_results.append(res)

        return final_results
