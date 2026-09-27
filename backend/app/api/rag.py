from typing import Optional, List
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from pydantic import BaseModel, Field
from app.rag.vector_engine import RAGEngine

router = APIRouter(prefix="/api/rag", tags=["知识库与向量检索 (RAG)"])

class SearchRequest(BaseModel):
    """知识库相似度检索入参 Schema"""
    query: str = Field(..., description="语义检索文本")
    top_k: int = Field(default=4, description="返回的相关切片最大数量")

class TextUploadRequest(BaseModel):
    """纯文本上传入库 Schema"""
    title: str = Field(..., description="文档标题")
    content: str = Field(..., description="文档正文内容")

@router.get("/documents")
async def list_documents():
    """
    获取本地向量库中所有已持久化的文档元数据汇总列表。
    """
    engine = RAGEngine.get_instance()
    docs = engine.list_documents()
    return {"documents": docs, "total": len(docs)}

@router.post("/upload/text")
async def upload_text(req: TextUploadRequest):
    """
    直接添加纯文本或 Markdown 代码片段到知识库，自动切分并向量化入库。
    """
    if not req.content.strip():
        raise HTTPException(status_code=400, detail="文档正文内容不能为空。")
    engine = RAGEngine.get_instance()
    result = engine.add_text_document(
        title=req.title or "未命名笔记",
        text=req.content,
        doc_type="text",
    )
    return result

@router.post("/upload/file")
async def upload_file(file: UploadFile = File(...)):
    """
    上传本地文件（PDF、Markdown、TXT、代码文件等），解析文本并写入本地向量数据库。
    """
    try:
        content_bytes = await file.read()
        filename = file.filename or "uploaded_file"
        ext = filename.split(".")[-1].lower() if "." in filename else ""

        if ext == "pdf" or (file.content_type and "pdf" in file.content_type):
            import io
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(content_bytes))
            if reader.is_encrypted:
                try:
                    reader.decrypt("")
                except Exception:
                    pass
            pages_text = []
            for i, page in enumerate(reader.pages):
                try:
                    t = page.extract_text() or ""
                    if t.strip():
                        pages_text.append(f"--- [PDF 第 {i+1} 页] ---\n{t.strip()}")
                except Exception:
                    pass
            text_content = "\n\n".join(pages_text)
        else:
            # 按 UTF-8 编码解码为字符串
            text_content = content_bytes.decode("utf-8", errors="replace")

        if not text_content.strip():
            raise HTTPException(status_code=400, detail="上传文件为空或无法解码为有效文本。")

        engine = RAGEngine.get_instance()
        result = engine.add_text_document(
            title=filename,
            text=text_content,
            doc_type=ext if ext else "file",
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文件处理发生异常: {str(e)}")

@router.post("/search")
async def search_knowledge(req: SearchRequest):
    """
    知识库语义检索调试接口：返回与输入 query 最相似的文本片段及其向量距离。
    """
    engine = RAGEngine.get_instance()
    results = engine.search_similar(query=req.query, top_k=req.top_k)
    return {"query": req.query, "results": results}

@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str):
    """
    根据文档唯一标识 doc_id，彻底清理该文档所属的全部向量切片。
    """
    engine = RAGEngine.get_instance()
    success = engine.delete_document(doc_id)
    return {"success": success, "doc_id": doc_id}

@router.post("/clear")
async def clear_knowledge():
    """
    清空整个本地知识库集合的所有数据。
    """
    engine = RAGEngine.get_instance()
    engine.clear_all()
    return {"success": True, "message": "本地知识库已全部清空。"}

@router.get("/backup/status")
async def get_backup_status():
    """
    【方案 C 灾备】获取知识库灾备快照状态与文档数量。
    """
    engine = RAGEngine.get_instance()
    snapshot = engine.backup_mgr.load_snapshot()
    docs = snapshot.get("documents", {})
    return {
        "success": True,
        "backup_docs_count": len(docs),
        "primary_backup_exists": engine.backup_mgr.primary_file.exists(),
        "primary_backup_path": str(engine.backup_mgr.primary_file),
        "redundant_backup_exists": engine.backup_mgr.redundant_file.exists(),
        "redundant_backup_path": str(engine.backup_mgr.redundant_file),
        "updated_at": snapshot.get("updated_at"),
    }

@router.post("/backup/restore")
async def restore_from_backup():
    """
    【方案 C 灾备】手动触发从快照恢复并满血重建 Milvus 向量库索引。
    """
    try:
        engine = RAGEngine.get_instance()
        recovered_chunks = engine.rebuild_from_snapshot()
        return {
            "success": True,
            "recovered_chunks": recovered_chunks,
            "message": f"成功从灾备快照中重建并恢复了 {recovered_chunks} 个向量切片！"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"恢复失败: {str(e)}")

@router.post("/backup/export")
async def export_backup():
    """
    【方案 C 灾备】导出知识库全量灾备包（方便电脑迁移与永久留存）。
    """
    try:
        engine = RAGEngine.get_instance()
        out_file = engine.backup_mgr.export_backup()
        return {
            "success": True,
            "exported_file": out_file,
            "message": "知识库全量灾备快照已导出完毕！"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导出备份失败: {str(e)}")

