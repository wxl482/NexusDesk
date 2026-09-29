import io
import json
import logging
from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Request, UploadFile, File
import pypdf
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse
from langchain_core.messages import HumanMessage, AIMessage

from app.agents.graph import create_agent_graph, memory_checkpointer
from app.agents.laya_service import laya_service
from app.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["对话与智能体调度"])

class LayaDecisionRequest(BaseModel):
    """Laya 决策请求 Schema"""
    text: str = Field(..., description="待评估或路由的指令文本")

class ChatRequest(BaseModel):
    """
    智能体对话请求体 Schema 定义
    """
    message: str = Field(..., description="用户输入的提问文本或操作指令")
    session_id: str = Field(default="default_session", description="会话唯一标识（对应 LangGraph thread_id）")
    mode: str = Field(default="react", description="智能体运行模式：'chat' | 'react' | 'multi_agent' | 'rag'")
    model: Optional[str] = Field(default=None, description="动态指定的大语言模型标识")
    base_url: Optional[str] = Field(default=None, description="动态覆盖的 API 基础路径")
    api_key: Optional[str] = Field(default=None, description="动态覆盖的 API Key")
    temperature: Optional[float] = Field(default=None, description="采样温度")
    approval_mode: Optional[str] = Field(default="smart", description="操作权限与审批模式：'ask_always' | 'smart' | 'full_access'")
    images: Optional[list[str]] = Field(default=None, description="多模态输入图片列表 (Base64 或 URL)")

_ACTIVE_THREADS: list[str] = []

def _record_and_prune_threads(thread_id: str, max_threads: int = 60):
    """LRU 会话内存清理：限制内存中保存的活跃 Thread 检查点数量，淘汰最久未访问会话"""
    global _ACTIVE_THREADS
    if thread_id in _ACTIVE_THREADS:
        _ACTIVE_THREADS.remove(thread_id)
    _ACTIVE_THREADS.append(thread_id)

    if len(_ACTIVE_THREADS) > max_threads:
        to_prune = _ACTIVE_THREADS[: len(_ACTIVE_THREADS) - max_threads]
        _ACTIVE_THREADS = _ACTIVE_THREADS[len(_ACTIVE_THREADS) - max_threads :]
        for old_tid in to_prune:
            try:
                if hasattr(memory_checkpointer, "delete_thread"):
                    memory_checkpointer.delete_thread(old_tid)
            except Exception:
                pass


@router.post("/stream")
async def chat_stream(req: ChatRequest):
    """
    基于 Server-Sent Events (SSE) 的全链路流式交互接口。
    实时推送 LangGraph 运行生命周期中的 Token 打字机流、工具调用状态以及节点流转事件。
    """
    # 动态记录活跃会话并自动修剪超期 Checkpoint，杜绝后端内存膨胀
    _record_and_prune_threads(req.session_id)

    # 智能模型动态路由 (Model Dynamic Router)
    from app.llm.router import ModelRouter
    routed_info = None
    target_model = req.model
    if not target_model or target_model in ["auto", "smart", "default", ""]:
        route_res = ModelRouter.route_prompt(req.message, req.model)
        target_model = route_res.get("model")
        routed_info = route_res

    # 根据请求参数构建并编译对应的状态图
    app_graph = create_agent_graph(
        model=target_model,
        base_url=req.base_url,
        api_key=req.api_key,
        temperature=req.temperature,
    )

    # 配置当前会话的 thread_id，实现记忆恢复与持久化
    config = {"configurable": {"thread_id": req.session_id}}

    # 构建用户提问消息：若包含图片则组装为 LangChain 多模态复合消息块
    if req.images and len(req.images) > 0:
        content_parts: list[dict[str, Any]] = []
        if req.message and req.message.strip():
            content_parts.append({"type": "text", "text": req.message.strip()})
        else:
            content_parts.append({"type": "text", "text": "请分析我上传的图片。"})
        for img in req.images:
            content_parts.append({
                "type": "image_url",
                "image_url": {"url": img}
            })
        human_msg = HumanMessage(content=content_parts)
    else:
        human_msg = HumanMessage(content=req.message)

    input_state = {
        "messages": [human_msg],
        "mode": req.mode,
        "approval_mode": req.approval_mode or "smart",
        "tool_steps": 0,  # 确保每一个新会话轮次，工具执行轮数强制从 0 重新计数
    }

    async def event_generator():
        """SSE 异步事件生成器"""
        in_dsml_block = False
        try:
            # 发送会话启动事件与动态模型分流事件
            yield {
                "event": "message",
                "data": json.dumps({
                    "type": "session_start",
                    "session_id": req.session_id,
                    "mode": req.mode,
                    "model": target_model,
                })
            }
            if routed_info:
                yield {
                    "event": "message",
                    "data": json.dumps({
                        "type": "model_routed",
                        "model": target_model,
                        "tier": routed_info.get("tier"),
                        "reason": routed_info.get("reason"),
                    })
                }

            # 监听 LangGraph v2 事件流
            async for event in app_graph.astream_events(input_state, config=config, version="v2"):
                kind = event["event"]
                name = event.get("name", "")
                data = event.get("data", {})

                # 1. 大模型 Token 流式输出
                if kind == "on_chat_model_stream":
                    chunk = data.get("chunk")
                    if chunk and hasattr(chunk, "content") and chunk.content:
                        # 兼容深度思考模型（如 DeepSeek 的 reasoning_content 思考链）
                        reasoning = getattr(chunk, "additional_kwargs", {}).get("reasoning_content")
                        if reasoning:
                            yield {
                                "event": "message",
                                "data": json.dumps({"type": "thought", "content": reasoning})
                            }
                        if isinstance(chunk.content, str) and chunk.content:
                            text_token = chunk.content
                            # 过滤并抑制 DeepSeek 原生 DSML XML 标记向客户端流式泄露
                            if "<|DSML" in text_token or "<｜DSML" in text_token or "<DSML" in text_token:
                                in_dsml_block = True
                            if in_dsml_block:
                                if "calls>" in text_token or "invoke>" in text_token:
                                    in_dsml_block = False
                                continue
                            yield {
                                "event": "message",
                                "data": json.dumps({"type": "token", "content": text_token})
                            }

                # 2. 外部工具开始调用事件
                elif kind == "on_tool_start":
                    yield {
                        "event": "message",
                        "data": json.dumps({
                            "type": "tool_start",
                            "tool": name,
                            "input": data.get("input", {}),
                        })
                    }

                # 3. 外部工具执行完毕并返回结果
                elif kind == "on_tool_end":
                    output = data.get("output", "")
                    output_str = str(output) if not isinstance(output, str) else output
                    # 超长结果适度截断，保证 SSE 传输流畅
                    if len(output_str) > 4000:
                        output_str = output_str[:4000] + "... (结果过长已截断)"
                    yield {
                        "event": "message",
                        "data": json.dumps({
                            "type": "tool_end",
                            "tool": name,
                            "output": output_str,
                        })
                    }

                # 4. 外部工具执行异常捕获并通知前端
                elif kind == "on_tool_error":
                    error_data = data.get("error", "工具调用发生异常")
                    error_str = str(error_data)
                    yield {
                        "event": "message",
                        "data": json.dumps({
                            "type": "tool_error",
                            "tool": name,
                            "error": error_str,
                        })
                    }

                # 5. LangGraph 节点生命周期状态流转
                elif kind == "on_chain_start" and name in ["agent", "tools"]:
                    yield {
                        "event": "message",
                        "data": json.dumps({"type": "node_start", "node": name})
                    }
                elif kind == "on_chain_end" and name in ["agent", "tools"]:
                    yield {
                        "event": "message",
                        "data": json.dumps({"type": "node_end", "node": name})
                    }

                # 5. 上下文自动压缩触发感知通知 (在思考链/状态流中实时展示)
                elif kind == "on_chain_end" and name == "compress_node":
                    output = data.get("output", {})
                    if output and isinstance(output, dict) and output.get("summary"):
                        yield {
                            "event": "message",
                            "data": json.dumps({
                                "type": "thought",
                                "content": "⚡ [系统：上下文自动压缩已触发] 检测到历史消息达到阈值，已提炼前序对话要点并精简上下文。\n\n"
                            })
                        }

                # 6. 长程任务规划状态机事件
                elif kind == "on_chain_end" and name == "planner_node":
                    output = data.get("output", {})
                    if output and isinstance(output, dict) and output.get("plan"):
                        yield {
                            "event": "message",
                            "data": json.dumps({
                                "type": "plan",
                                "plan": output.get("plan"),
                            })
                        }



            # 发送流式结束事件
            yield {
                "event": "message",
                "data": json.dumps({"type": "done", "session_id": req.session_id})
            }

        except Exception as e:
            logger.error(f"SSE 流式生成异常: {e}", exc_info=True)
            yield {
                "event": "message",
                "data": json.dumps({
                    "type": "error",
                    "error": str(e),
                    "hint": "请检查【模型设置】中的 API Key、Base URL 或网络代理是否配置正确。"
                })
            }

    return EventSourceResponse(event_generator())


@router.post("/parse-file")
async def parse_file(file: UploadFile = File(...)):
    """
    解析用户上传的文件（支持 PDF、Word .docx、Excel .xlsx、CSV、Markdown、纯文本、代码文件等），
    提取格式化 Markdown 内容与元数据，以便前端直接作为文档上下文传给 Agent。
    """
    try:
        from app.rag.doc_parser import parse_document
        content_bytes = await file.read()
        filename = file.filename or "uploaded_file"
        file_size = len(content_bytes)
        ext = filename.split(".")[-1].lower() if "." in filename else ""

        parsed = parse_document(content_bytes, filename)
        if not parsed.get("success"):
            raise HTTPException(status_code=400, detail=parsed.get("error", "文件解析失败"))

        return {
            "name": filename,
            "size": file_size,
            "type": parsed.get("doc_type", ext or "text"),
            "is_pdf": (ext == "pdf"),
            "pages": 1,
            "text": parsed.get("text", ""),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"解析文件失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"文件解析失败: {str(e)}")


@router.get("/history/{session_id}")
async def get_history(session_id: str):
    """
    根据 session_id 从持久化检查点中提取当前会话的历史消息记录。
    """
    try:
        config = {"configurable": {"thread_id": session_id}}
        state = memory_checkpointer.get(config)
        if not state or "channel_values" not in state or "messages" not in state["channel_values"]:
            return {"session_id": session_id, "messages": []}

        messages = state["channel_values"]["messages"]
        serialized = []
        for m in messages:
            role = "user" if isinstance(m, HumanMessage) else "assistant" if isinstance(m, AIMessage) else "system"
            content = m.content
            images = []
            if isinstance(content, list):
                text_parts = []
                for part in content:
                    if isinstance(part, dict):
                        if part.get("type") == "text":
                            text_parts.append(part.get("text", ""))
                        elif part.get("type") == "image_url":
                            img_obj = part.get("image_url", {})
                            url = img_obj.get("url") if isinstance(img_obj, dict) else str(img_obj)
                            if url:
                                images.append(url)
                content = "\n".join(text_parts)
            serialized.append({
                "role": role,
                "content": content if isinstance(content, str) else str(content),
                "images": images,
            })
        return {"session_id": session_id, "messages": serialized}
    except Exception as e:
        return {"session_id": session_id, "messages": [], "error": str(e)}


@router.delete("/sessions/{session_id}")
async def delete_session_checkpoint(session_id: str):
    """
    清理指定 session_id 在后端 Checkpointer 中的内存状态，防止长期运行时内存泄漏。
    """
    try:
        if hasattr(memory_checkpointer, "delete_thread"):
            memory_checkpointer.delete_thread(session_id)
        elif hasattr(memory_checkpointer, "storage"):
            keys_to_del = [k for k in memory_checkpointer.storage.keys() if k == session_id or (isinstance(k, tuple) and k and k[0] == session_id)]
            for k in keys_to_del:
                memory_checkpointer.storage.pop(k, None)
        return {"status": "ok", "deleted_session": session_id}
    except Exception as e:
        logger.warning(f"清理会话 {session_id} 异常: {e}")
        return {"status": "error", "error": str(e)}


@router.post("/laya-decision")
async def test_laya_decision(req: LayaDecisionRequest):
    """
    Laya 毫秒级决策测试接口 (供前端或开发者实时验证与基准测试)。
    """
    res = laya_service.predict_intent_and_agent(req.text)
    return {"code": 200, "data": res}

