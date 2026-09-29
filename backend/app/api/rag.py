from typing import Optional, List
from fastapi import APIRouter, UploadFile, File, Form, Query, HTTPException
from pydantic import BaseModel, Field
from app.rag.vector_engine import RAGEngine
from app.rag.doc_parser import parse_document

router = APIRouter(prefix="/api/rag", tags=["知识库与向量检索 (RAG)"])

class SearchRequest(BaseModel):
    """知识库相似度检索入参 Schema"""
    query: str = Field(..., description="语义检索文本")
    top_k: int = Field(default=4, description="返回的相关切片最大数量")
    category: Optional[str] = Field(default=None, description="知识库分类/集合标签")

class TextUploadRequest(BaseModel):
    """纯文本上传入库 Schema"""
    title: str = Field(..., description="文档标题")
    content: str = Field(..., description="文档正文内容")
    category: Optional[str] = Field(default="default", description="知识库分类/集合标签")

@router.get("/documents")
async def list_documents(category: Optional[str] = Query(None, description="分类过滤")):
    """
    获取本地向量库中所有已持久化的文档元数据汇总列表（支持按 category 分类过滤）。
    """
    engine = RAGEngine.get_instance()
    docs = engine.list_documents(category=category)
    return {"documents": docs, "total": len(docs), "category": category}

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
        category=req.category or "default",
    )
    return result

@router.post("/upload/file")
async def upload_file(
    file: UploadFile = File(...),
    category: Optional[str] = Form("default"),
):
    """
    上传本地文件（PDF、Word .docx、Excel .xlsx、CSV、Markdown、TXT、代码文件等），
    使用工业级多格式解析器解析正文与结构化表格，并写入向量库与 BM25 索引。
    """
    try:
        content_bytes = await file.read()
        filename = file.filename or "uploaded_file"

        parsed = parse_document(content_bytes, filename)
        if not parsed.get("success") or not parsed.get("text"):
            err_msg = parsed.get("error", "上传文件为空或无法解码为有效文本。")
            raise HTTPException(status_code=400, detail=err_msg)

        text_content = parsed["text"]
        doc_type = parsed.get("doc_type", "file")

        engine = RAGEngine.get_instance()
        result = engine.add_text_document(
            title=filename,
            text=text_content,
            doc_type=doc_type,
            category=category or "default",
        )
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("message", "文档写入向量库失败"))

        result["parsed_type"] = doc_type
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文件处理发生异常: {str(e)}")

@router.post("/search")
async def search_knowledge(req: SearchRequest):
    """
    知识库语义检索调试接口：返回与输入 query 最相似的文本片段及其向量距离与 BM25/RRF 评分。
    """
    engine = RAGEngine.get_instance()
    results = engine.search_similar(query=req.query, top_k=req.top_k, category=req.category)
    return {"query": req.query, "category": req.category, "results": results}

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

