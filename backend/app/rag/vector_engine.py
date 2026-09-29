import os
import uuid
import json
import time
from pathlib import Path
from typing import List, Dict, Any, Optional

# 防御性配置：避免 Milvus 与其他底层科学计算库在 macOS 下重复加载 libomp 冲突
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["OMP_NUM_THREADS"] = "1"

# 引入 LangChain 核心向量检索与文档抽象
from langchain_milvus import Milvus
from langchain_openai import OpenAIEmbeddings
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.tools import tool

from app.core.config import settings
from app.core.logger import logger
from app.rag.hybrid_retriever import ChineseBM25Retriever, HybridRAGFusion


class ZhipuEmbeddings(Embeddings):
    """
    智谱 AI embedding-3 官方兼容向量化适配器。
    基于标准 OpenAI 兼容协议接入智谱开放平台，输出 2048 维高精度稠密向量。
    """
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or settings.ZHIPUAI_API_KEY or os.getenv("ZHIPUAI_API_KEY", "")
        self.model = model or settings.EMBEDDING_MODEL
        self.base_url = "https://open.bigmodel.cn/api/paas/v4/"
        key_to_use = self.api_key if (self.api_key and self.api_key.strip()) else "sk-no-key-provided"
        self._client = OpenAIEmbeddings(
            model=self.model,
            api_key=key_to_use,
            base_url=self.base_url,
            check_embedding_ctx_length=False,
        )

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """批量计算文档嵌入向量"""
        return self._client.embed_documents(texts)

    def embed_query(self, text: str) -> List[float]:
        """计算单条查询嵌入向量"""
        return self._client.embed_query(text)


class LocalChromadbEmbeddings(Embeddings):
    """向后兼容保留的本地嵌入类"""
    def __init__(self):
        try:
            import chromadb.utils.embedding_functions as ef
            self.ef = ef.DefaultEmbeddingFunction()
        except Exception:
            self.ef = None

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self.ef(texts) if self.ef else [[0.0] * 384 for _ in texts]

    def embed_query(self, text: str) -> List[float]:
        return self.ef([text])[0] if self.ef else [0.0] * 384


class KnowledgeBackupManager:
    """
    【方案 C 核心防丢失系统】
    知识库全量快照与灾备容灾管理器。
    实现“双写快照 + 冗余备份 + 自动自愈重建”，彻底解决本地向量库误删导致数据丢失的问题。
    """
    def __init__(self, backup_dir: Path, user_backup_dir: Path):
        self.primary_file = backup_dir / "knowledge_snapshot.json"
        self.redundant_file = user_backup_dir / "knowledge_snapshot.json"
        self.backup_dir = backup_dir
        self.user_backup_dir = user_backup_dir

    def _read_json(self, file_path: Path) -> Optional[Dict[str, Any]]:
        if file_path.exists():
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"[BackupManager] 读取快照文件 {file_path} 失败: {e}")
        return None

    def _write_json(self, file_path: Path, data: Dict[str, Any]) -> bool:
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"[BackupManager] 写入快照文件 {file_path} 失败: {e}")
            return False

    def load_snapshot(self) -> Dict[str, Any]:
        """优先读取主备份，若缺失则读取系统冗余备份"""
        data = self._read_json(self.primary_file)
        if data is None:
            data = self._read_json(self.redundant_file)
            if data:
                logger.info("[BackupManager] 主快照缺失，成功从系统级冗余快照恢复数据。")
                self._write_json(self.primary_file, data)
        return data or {"version": "1.0", "updated_at": time.time(), "documents": {}}

    def save_document_snapshot(self, doc_id: str, title: str, doc_type: str, chunks: List[Document], category: str = "default"):
        """双写保存文档及其切片快照（含多知识库/分类标识）"""
        data = self.load_snapshot()
        data["updated_at"] = time.time()
        chunk_data = [
            {
                "chunk_index": i,
                "page_content": c.page_content,
                "metadata": c.metadata or {}
            }
            for i, c in enumerate(chunks)
        ]
        data["documents"][doc_id] = {
            "doc_id": doc_id,
            "title": title,
            "doc_type": doc_type,
            "category": category,
            "created_at": time.time(),
            "chunks_count": len(chunks),
            "chunks": chunk_data,
        }
        self._write_json(self.primary_file, data)
        self._write_json(self.redundant_file, data)

    def delete_document_snapshot(self, doc_id: str):
        """同步从快照中移除文档"""
        data = self.load_snapshot()
        if doc_id in data.get("documents", {}):
            del data["documents"][doc_id]
            data["updated_at"] = time.time()
            self._write_json(self.primary_file, data)
            self._write_json(self.redundant_file, data)

    def list_documents(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """高速读取文档元数据列表，支持分类过滤"""
        data = self.load_snapshot()
        results = []
        for doc_id, info in data.get("documents", {}).items():
            doc_cat = info.get("category", "default")
            if category and doc_cat != category:
                continue
            results.append({
                "doc_id": doc_id,
                "title": info.get("title", "未命名文档"),
                "doc_type": info.get("doc_type", "text"),
                "category": doc_cat,
                "chunks": info.get("chunks_count", len(info.get("chunks", []))),
                "created_at": info.get("created_at", 0),
            })
        return results

    def clear_all(self):
        """清空快照"""
        empty_data = {"version": "1.0", "updated_at": time.time(), "documents": {}}
        self._write_json(self.primary_file, empty_data)
        self._write_json(self.redundant_file, empty_data)

    def export_backup(self, target_path: Optional[str] = None) -> str:
        """导出全量备份 JSON 到指定路径"""
        data = self.load_snapshot()
        out_path = Path(target_path) if target_path else self.backup_dir / f"nexusdesk_knowledge_backup_{int(time.time())}.json"
        self._write_json(out_path, data)
        return str(out_path)

    def import_backup(self, source_path: str) -> Dict[str, Any]:
        """从外部备份 JSON 载入数据并持久化"""
        data = self._read_json(Path(source_path))
        if not data or "documents" not in data:
            raise ValueError("备份文件内容无效或格式不正确。")
        self._write_json(self.primary_file, data)
        self._write_json(self.redundant_file, data)
        return data


class RAGEngine:
    """
    基于 LangChain Milvus 封装的轻量级与灾备容灾增强检索增强 (RAG) 引擎。
    采用 智谱 AI embedding-3 (2048维) + Milvus Lite 向量引擎，
    并挂载全自动双写备份快照与自愈机制（方案 C），兼顾极致检索精度与数据安全。
    """
    _instance: Optional["RAGEngine"] = None

    def __init__(self):
        # 1. 向量持久化存储参数
        self.milvus_uri = str(settings.MILVUS_URI)
        self.collection_name = "nexusdesk_knowledge"
        
        # 确保本地数据库目录存在
        if not self.milvus_uri.startswith("http://") and not self.milvus_uri.startswith("https://"):
            Path(self.milvus_uri).parent.mkdir(parents=True, exist_ok=True)

        # 2. 灾备管理器初始化
        self.backup_mgr = KnowledgeBackupManager(
            backup_dir=settings.BACKUP_PATH,
            user_backup_dir=settings.USER_BACKUP_PATH
        )

        # 3. 构造 智谱 AI Embeddings 实例 (2048 维度)
        self.embedding_function = ZhipuEmbeddings()

        # 4. 构造 LangChain 官方 Milvus 向量库连接
        connection_args = {"uri": self.milvus_uri}
        if settings.MILVUS_TOKEN:
            connection_args["token"] = settings.MILVUS_TOKEN

        self.vector_store = Milvus(
            embedding_function=self.embedding_function,
            connection_args=connection_args,
            collection_name=self.collection_name,
            auto_id=True,
        )

        # 5. 配置 Parent-Child 双层分块切割器（父切片宽上下文 + 子切片高精度索引）
        self.parent_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1200,
            chunk_overlap=150,
            separators=["\n\n", "\n", "。", "！", "？", ".", " ", ""],
        )
        self.child_splitter = RecursiveCharacterTextSplitter(
            chunk_size=300,
            chunk_overlap=50,
            separators=["\n\n", "\n", "。", "！", "？", ".", " ", ""],
        )
        self.text_splitter = self.child_splitter

        # 6. 初始化 BM25 稀疏检索器与 RRF 倒数排名融合器
        self.bm25_retriever = ChineseBM25Retriever()
        self.hybrid_fusion = HybridRAGFusion(rrf_k=60)

        # 7. 执行启动时自愈检查与 BM25 索引构建
        self.auto_recover_if_needed()
        self._refresh_bm25_index()

    @classmethod
    def get_instance(cls) -> "RAGEngine":
        """获取 RAG 引擎的全局单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _refresh_bm25_index(self):
        """从本地备份快照中汇总所有切片并构建 BM25 关键词倒排索引"""
        try:
            snapshot_docs = self.backup_mgr.load_snapshot().get("documents", {})
            all_chunks = []
            for doc_id, doc_info in snapshot_docs.items():
                category = doc_info.get("category", "default")
                for c in doc_info.get("chunks", []):
                    c_meta = dict(c.get("metadata", {}))
                    c_meta["category"] = category
                    all_chunks.append({
                        "page_content": c.get("page_content", ""),
                        "metadata": c_meta
                    })
            self.bm25_retriever.build_index(all_chunks)
        except Exception as e:
            logger.warning(f"[RAGEngine] 刷新 BM25 索引异常: {e}")

    def auto_recover_if_needed(self):
        """
        方案 C 核心防丢逻辑：
        如果 Milvus 集合为空（例如本地 db 文件被误删或损坏），但快照中仍有备份文档，
        系统自动在后台执行自愈重建，满血恢复全部向量数据。
        """
        try:
            snapshot_docs = self.backup_mgr.load_snapshot().get("documents", {})
            if not snapshot_docs:
                return

            # 探测 Milvus 当前是否为空
            sample_search = self.vector_store.similarity_search("探测", k=1)
            if not sample_search and len(snapshot_docs) > 0:
                logger.info(f"[RAGEngine] 检测到本地 Milvus 集合缺失，正在从灾备快照自动重建 {len(snapshot_docs)} 篇文档...")
                self.rebuild_from_snapshot()
        except Exception as e:
            logger.warning(f"[RAGEngine] 自动自愈检查跳过: {e}")

    def rebuild_from_snapshot(self) -> int:
        """从快照重新生成并写入所有向量到 Milvus，并同步重建 BM25 索引"""
        snapshot_docs = self.backup_mgr.load_snapshot().get("documents", {})
        total_chunks = 0
        for doc_id, doc_info in snapshot_docs.items():
            chunks_raw = doc_info.get("chunks", [])
            docs_to_add = [
                Document(
                    page_content=c["page_content"],
                    metadata=c.get("metadata", {})
                )
                for c in chunks_raw
            ]
            if docs_to_add:
                self.vector_store.add_documents(docs_to_add)
                total_chunks += len(docs_to_add)
        self._refresh_bm25_index()
        logger.info(f"[RAGEngine] 灾备自愈重建完成！成功恢复 {len(snapshot_docs)} 篇文档，共 {total_chunks} 个切片。")
        return total_chunks

    def get_retriever(self, top_k: int = 4):
        """
        获取 LangChain 标准检索器 (BaseRetriever)。
        可直接用于 LCEL 管道: `retriever | prompt | llm | StrOutputParser()`
        """
        return self.vector_store.as_retriever(search_kwargs={"k": top_k})

    def add_text_document(self, title: str, text: str, doc_type: str = "text", category: str = "default") -> Dict[str, Any]:
        """
        【P0 父子切片与混合索引入库】
        1. 使用 parent_splitter 切割大上下文切片 (~1200 字符)；
        2. 对每个父切片，使用 child_splitter 切割高精度子切片 (~300 字符)；
        3. 子切片向量化写入 Milvus 稠密库（附带 parent_content 元数据）；
        4. 同步持久化灾备快照并更新 BM25 关键词倒排索引。
        """
        text_clean = text.strip()
        if not text_clean:
            return {"success": False, "chunks": 0, "message": "文档内容为空或无有效文本。"}

        doc_id = str(uuid.uuid4())
        parent_chunks = self.parent_splitter.split_text(text_clean)
        if not parent_chunks:
            parent_chunks = [text_clean]

        documents: List[Document] = []
        overall_idx = 0

        for p_idx, p_content in enumerate(parent_chunks):
            # 对单个父块再切分子切片
            if len(p_content) <= 350:
                c_chunks = [p_content]
            else:
                c_chunks = self.child_splitter.split_text(p_content)
                if not c_chunks:
                    c_chunks = [p_content]

            for c_content in c_chunks:
                doc_obj = Document(
                    page_content=c_content,
                    metadata={
                        "doc_id": doc_id,
                        "title": title,
                        "doc_type": doc_type,
                        "category": category,
                        "chunk_index": overall_idx,
                        "parent_id": f"{doc_id}_p{p_idx}",
                        "parent_content": p_content,
                    }
                )
                documents.append(doc_obj)
                overall_idx += 1

        # 1. 批量写入 Milvus
        self.vector_store.add_documents(documents)

        # 2. 同步双写灾备快照（方案 C：即使 db 文件被删，快照随时可还原）
        self.backup_mgr.save_document_snapshot(
            doc_id=doc_id,
            title=title,
            doc_type=doc_type,
            chunks=documents,
            category=category,
        )

        # 3. 动态刷新内存中的 BM25 关键词倒排索引
        self._refresh_bm25_index()

        logger.info(f"[RAGEngine] 文档 《{title}》 成功存入 Milvus 与灾备快照 (父切片: {len(parent_chunks)}, 子切片: {len(documents)}, 分类: {category})")

        return {
            "success": True,
            "doc_id": doc_id,
            "title": title,
            "category": category,
            "parent_chunks_count": len(parent_chunks),
            "chunks_count": len(documents),
        }

    def search_similar(
        self,
        query: str,
        top_k: int = 4,
        category: Optional[str] = None,
        score_threshold: float = 1.6
    ) -> List[Dict[str, Any]]:
        """
        【P0 工业级 Milvus + BM25 混合检索与 RRF 融合排序】
        1. 稠密多维语义召回 (Milvus + 智谱 embedding-3)；
        2. 稀疏关键词精准召回 (Jieba + BM25Okapi)；
        3. Reciprocal Rank Fusion (RRF) 倒数排名打分重排；
        4. 自动解包父切片 (Parent-Child Chunking)，向模型呈现实质性丰富上下文。
        """
        candidate_k = max(top_k * 3, 6)

        # 1. 稠密向量检索
        dense_results: List[Dict[str, Any]] = []
        try:
            raw_results = self.vector_store.similarity_search_with_score(query, k=candidate_k)
            for doc, score in raw_results:
                dist = float(score)
                meta = doc.metadata or {}
                doc_cat = meta.get("category", "default")
                if category and doc_cat != category:
                    continue
                if dist > score_threshold:
                    continue
                dense_results.append({
                    "content": doc.page_content,
                    "title": meta.get("title", "未知来源"),
                    "doc_id": meta.get("doc_id", ""),
                    "category": doc_cat,
                    "chunk_index": meta.get("chunk_index", 0),
                    "parent_content": meta.get("parent_content"),
                    "distance": round(dist, 4),
                })
        except Exception as e:
            logger.error(f"[RAGEngine] Milvus 稠密检索异常: {e}")

        # 2. 稀疏 BM25 关键词检索
        sparse_results: List[Tuple[Dict[str, Any], float]] = []
        try:
            sparse_results = self.bm25_retriever.search(query, top_k=candidate_k, category=category)
        except Exception as e:
            logger.error(f"[RAGEngine] BM25 稀疏检索异常: {e}")

        # 3. 若 BM25 与向量均有效，使用 RRF 混合融合算法
        if dense_results or sparse_results:
            fused = self.hybrid_fusion.fuse(dense_results, sparse_results, top_k=top_k)
            if fused:
                return fused

        # 降级兜底：返回稠密检索结果前 top_k 条
        return dense_results[:top_k]

    def list_documents(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        获取知识库中所有文档的元数据概要列表，支持分类过滤。
        直接从快照管理器高速读取，极速响应。
        """
        return self.backup_mgr.list_documents(category=category)

    def delete_document(self, doc_id: str) -> bool:
        """从 Milvus 与灾备快照中同步删除指定文档，并更新 BM25 索引"""
        try:
            # 1. 从 Milvus 中删除切片
            expr = f'doc_id == "{doc_id}"'
            self.vector_store.delete(expr=expr)
            # 2. 从快照中删除
            self.backup_mgr.delete_document_snapshot(doc_id)
            # 3. 刷新 BM25 索引
            self._refresh_bm25_index()
            logger.info(f"[RAGEngine] 成功删除文档 doc_id={doc_id}")
            return True
        except Exception as e:
            logger.error(f"[RAGEngine] 删除文档失败: {e}")
            return False

    def clear_all(self):
        """清空向量知识库中的全部记录与快照"""
        try:
            # 重置集合
            connection_args = {"uri": self.milvus_uri}
            if settings.MILVUS_TOKEN:
                connection_args["token"] = settings.MILVUS_TOKEN
            self.vector_store = Milvus(
                embedding_function=self.embedding_function,
                connection_args=connection_args,
                collection_name=self.collection_name,
                auto_id=True,
                drop_old=True,
            )
            self.backup_mgr.clear_all()
            self._refresh_bm25_index()
            logger.info("[RAGEngine] 知识库已全部清空。")
        except Exception as e:
            logger.error(f"[RAGEngine] 清空知识库失败: {e}")


# 封装为标准的 LangChain Tool
@tool
def query_knowledge_base(query: str) -> str:
    """
    检索本地私有 RAG 知识库，查找用户上传的文档、参考材料、专有知识或历史笔记。
    当提问涉及私有领域文档或特定文件时，优先调用此工具检索事实依据。

    参数:
        query: 检索关键词或问句
    """
    engine = RAGEngine.get_instance()
    docs = engine.list_documents()
    if not docs:
        return "本地知识库当前为空（尚未上传任何文档）。如果用户询问私有资料，请明确告知当前知识库暂无相关文档。"

    results = engine.search_similar(query, top_k=3)
    if not results:
        return f"知识库中未检索到与 '{query}' 相关的有效片段。建议尝试更简短明确的关键词，或向用户说明未找到匹配内容。"

    output_lines = [f"从本地知识库 (Milvus + 智谱 embedding-3) 中匹配到 {len(results)} 条高相关度片段:"]
    for i, r in enumerate(results, 1):
        output_lines.append(f"[{i}] 来源文档: 《{r['title']}》 (匹配距离: {r['distance']})")
        output_lines.append(f"{r['content']}\n")
    return "\n".join(output_lines)
