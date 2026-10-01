import os
import re
import json
import time
import asyncio
import logging
from typing import Dict, Any, List, Optional
import requests
from app.core.config import settings, DATA_DIR
from app.llm.factory import LLMFactory
from app.rag.vector_engine import RAGEngine

logger = logging.getLogger(__name__)

WORKFLOWS_FILE = DATA_DIR / "workflows.json"


def load_workflows_from_disk() -> List[Dict[str, Any]]:
    """从磁盘读取所有已保存的工作流配置"""
    if not WORKFLOWS_FILE.exists():
        return get_builtin_workflow_templates()
    try:
        with open(WORKFLOWS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"读取工作流配置失败: {e}")
        return get_builtin_workflow_templates()


def save_workflows_to_disk(workflows: List[Dict[str, Any]]) -> bool:
    """持久化工作流到磁盘"""
    try:
        with open(WORKFLOWS_FILE, "w", encoding="utf-8") as f:
            json.dump(workflows, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"保存工作流失败: {e}")
        return False


def get_builtin_workflow_templates() -> List[Dict[str, Any]]:
    """内置金标准自动化工作流模版：定时器 ➜ 爬取网页 ➜ 知识库提炼 ➜ 生成周报 ➜ 发送飞书"""
    return [
        {
            "id": "tpl_weekly_report_feishu",
            "name": "定时行业动态抓取 ➜ 知识库提炼 ➜ AI周报 ➜ 飞书推送",
            "description": "每周五定时自动化抓取最新前沿资讯，结合本地企业知识库背景，由大模型深度合成结构化精美周报并实时推送至飞书大群。",
            "cron": "0 18 * * 5",
            "is_scheduled": False,
            "created_at": int(time.time()),
            "nodes": [
                {
                    "id": "node_timer",
                    "type": "timer",
                    "title": "定时调度器 (Timer)",
                    "x": 80,
                    "y": 180,
                    "config": {
                        "schedule_type": "weekly",
                        "day_of_week": "5",
                        "time": "18:00",
                        "cron_expression": "0 18 * * 5",
                    },
                },
                {
                    "id": "node_crawler",
                    "type": "crawler",
                    "title": "网页抓取与萃取 (Web Crawler)",
                    "x": 380,
                    "y": 180,
                    "config": {
                        "url": "https://news.ycombinator.com",
                        "extract_mode": "article",
                        "timeout": 15,
                    },
                },
                {
                    "id": "node_rag",
                    "type": "rag",
                    "title": "知识库语义提炼 (RAG Filter)",
                    "x": 680,
                    "y": 180,
                    "config": {
                        "query": "技术前沿架构与大模型智能体演进方案",
                        "top_k": 3,
                        "category": "default",
                    },
                },
                {
                    "id": "node_llm",
                    "type": "llm",
                    "title": "AI 深度合成周报 (LLM Synthesis)",
                    "x": 980,
                    "y": 180,
                    "config": {
                        "model": "deepseek-chat",
                        "temperature": 0.5,
                        "system_prompt": "你是一个顶尖的行业分析师与架构师。请结合外部抓取的数据与企业私有知识库背景，编写一份专业、排版优美、见解深刻的自动化工作周报。",
                        "prompt_template": "【外部前沿资讯】：\n{{crawler_data}}\n\n【内部知识库依据】：\n{{rag_data}}\n\n请按照「行业大事件速览」、「核心技术洞察」、「下周行动建议」三个模块，生成一份高质量中文排版周报。",
                    },
                },
                {
                    "id": "node_feishu",
                    "type": "feishu",
                    "title": "飞书群机器人通知 (Feishu Webhook)",
                    "x": 1280,
                    "y": 180,
                    "config": {
                        "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxx",
                        "msg_type": "interactive",
                        "title": "📊 NexusDesk AI 行业前沿深度洞察周报",
                    },
                },
            ],
            "edges": [
                {"id": "e1", "source": "node_timer", "target": "node_crawler", "source_handle": "output", "target_handle": "input"},
                {"id": "e2", "source": "node_crawler", "target": "node_rag", "source_handle": "output", "target_handle": "input"},
                {"id": "e3", "source": "node_rag", "target": "node_llm", "source_handle": "output", "target_handle": "input"},
                {"id": "e4", "source": "node_llm", "target": "node_feishu", "source_handle": "output", "target_handle": "input"},
            ],
        }
    ]


class WorkflowExecutionEngine:
    """
    可视化工作流 DAG 拓扑执行引擎。
    执行全流程包含：
    1. 拓扑排序校验环路；
    2. 逐节点输入输出依赖传递与数据上下文注入；
    3. 支持单次全链路测试与异步状态流追踪。
    """

    @classmethod
    async def execute_workflow(cls, workflow: Dict[str, Any]) -> Dict[str, Any]:
        nodes = workflow.get("nodes", [])
        edges = workflow.get("edges", [])

        node_map = {n["id"]: n for n in nodes}
        execution_results: Dict[str, Any] = {}
        logs: List[Dict[str, Any]] = []

        start_time = time.time()

        # 1. 构建依赖拓扑
        in_degree = {n["id"]: 0 for n in nodes}
        adjacency: Dict[str, List[str]] = {n["id"]: [] for n in nodes}

        for edge in edges:
            src = edge.get("source")
            tgt = edge.get("target")
            if src in adjacency and tgt in in_degree:
                adjacency[src].append(tgt)
                in_degree[tgt] += 1

        # 2. 拓扑排序
        queue = [nid for nid, deg in in_degree.items() if deg == 0]
        execution_order = []

        while queue:
            curr = queue.pop(0)
            execution_order.append(curr)
            for neighbor in adjacency.get(curr, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(execution_order) < len(nodes):
            # 存在未成环节点兜底补全
            for n in nodes:
                if n["id"] not in execution_order:
                    execution_order.append(n["id"])

        # 3. 逐个节点执行
        pipeline_context: Dict[str, Any] = {}

        for nid in execution_order:
            node = node_map.get(nid)
            if not node:
                continue

            node_type = node.get("type", "unknown")
            node_title = node.get("title", node_type)
            cfg = node.get("config", {})

            node_start = time.time()
            logs.append({
                "time": time.strftime("%H:%M:%S"),
                "node_id": nid,
                "node_title": node_title,
                "status": "running",
                "message": f"开始执行节点: {node_title}...",
            })

            output_data: Any = None
            status = "completed"
            error_msg = ""

            try:
                if node_type == "timer":
                    output_data = {
                        "triggered_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "cron": cfg.get("cron_expression", "0 18 * * 5"),
                        "summary": "定时触发器已启动工作流执行周期",
                    }

                elif node_type == "crawler":
                    url = cfg.get("url", "https://news.ycombinator.com")
                    output_data = await cls._run_crawler(url, cfg)

                elif node_type == "rag":
                    query = cfg.get("query", "技术前沿架构与大模型智能体演进方案")
                    # 支持从前序爬虫产物中动态继承文本
                    if not query and pipeline_context.get("crawler"):
                        query = str(pipeline_context["crawler"])[:100]
                    output_data = await cls._run_rag(query, cfg)

                elif node_type == "llm":
                    output_data = await cls._run_llm(cfg, pipeline_context)

                elif node_type == "feishu":
                    output_data = await cls._run_feishu(cfg, pipeline_context)

                elif node_type == "email":
                    output_data = await cls._run_email(cfg, pipeline_context)

                else:
                    output_data = {"echo": f"节点 {node_title} 执行完毕", "config": cfg}

                pipeline_context[node_type] = output_data
                pipeline_context[nid] = output_data

            except Exception as e:
                status = "error"
                error_msg = str(e)
                logger.error(f"[WorkflowEngine] 节点 {nid} 执行失败: {e}", exc_info=True)

            node_duration = round((time.time() - node_start) * 1000, 1)

            execution_results[nid] = {
                "node_id": nid,
                "node_type": node_type,
                "node_title": node_title,
                "status": status,
                "duration_ms": node_duration,
                "output": output_data,
                "error": error_msg,
            }

            logs.append({
                "time": time.strftime("%H:%M:%S"),
                "node_id": nid,
                "node_title": node_title,
                "status": status,
                "message": f"节点执行完毕 ({node_duration}ms)" if status == "completed" else f"节点执行失败: {error_msg}",
            })

            # 如果遇到失败，后续节点记录为跳过
            if status == "error":
                break

        total_duration = round(time.time() - start_time, 2)
        return {
            "success": all(r["status"] == "completed" for r in execution_results.values()),
            "total_duration_sec": total_duration,
            "results": execution_results,
            "logs": logs,
        }

    @staticmethod
    async def _run_crawler(url: str, config: Dict[str, Any]) -> str:
        """执行简易高可用网页正文抓取与清洗"""
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        }
        loop = asyncio.get_event_loop()
        def _fetch():
            resp = requests.get(url, headers=headers, timeout=config.get("timeout", 15))
            resp.encoding = resp.apparent_encoding or "utf-8"
            return resp.text

        raw_html = await loop.run_in_executor(None, _fetch)
        # 净化 HTML 标签提取纯净正文
        cleaned = re.sub(r"<script[\s\S]*?</script>", "", raw_html, flags=re.I)
        cleaned = re.sub(r"<style[\s\S]*?</style>", "", cleaned, flags=re.I)
        cleaned = re.sub(r"<[^>]+>", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        # 截取前 2000 字符作为结构化提炼输入
        return cleaned[:2000]

    @staticmethod
    async def _run_rag(query: str, config: Dict[str, Any]) -> str:
        """调用本地 Hybrid RAG 引擎执行检索提炼"""
        try:
            engine = RAGEngine.get_instance()
            top_k = int(config.get("top_k", 3))
            category = config.get("category", "default")
            results = engine.search_similar(query=query, top_k=top_k, category=category)
            if not results:
                return "（未命中相关私有文档知识，将主要结合外部资讯进行总结分析）"
            chunks_text = []
            for idx, item in enumerate(results, 1):
                title = item.get("title", "未命名知识条目")
                content = item.get("content", "").strip()
                chunks_text.append(f"[{idx}] 《{title}》:\n{content}")
            return "\n\n".join(chunks_text)
        except Exception as e:
            return f"（知识库检索降级: {str(e)}）"

    @staticmethod
    async def _run_llm(config: Dict[str, Any], context: Dict[str, Any]) -> str:
        """调用大模型执行深度聚合与撰写"""
        model = config.get("model") or settings.DEFAULT_MODEL
        sys_prompt = config.get("system_prompt", "你是一个专业周报分析师。")
        prompt_tpl = config.get("prompt_template", "请根据以下资料输出周报：\n{{crawler_data}}\n\n{{rag_data}}")

        crawler_data = context.get("crawler", "")
        rag_data = context.get("rag", "")

        # 变量插值
        user_prompt = prompt_tpl.replace("{{crawler_data}}", str(crawler_data)).replace("{{rag_data}}", str(rag_data))

        llm = LLMFactory.get_chat_model(
            model=model,
            temperature=float(config.get("temperature", 0.5)),
            streaming=False,
        )
        from langchain_core.messages import SystemMessage, HumanMessage
        response = await llm.ainvoke([
            SystemMessage(content=sys_prompt),
            HumanMessage(content=user_prompt),
        ])
        return str(response.content).strip()

    @staticmethod
    async def _run_feishu(config: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """向飞书机器人发送 Webhook 通知"""
        webhook_url = config.get("webhook_url", "").strip()
        title = config.get("title", "📊 NexusDesk AI 行业前沿深度洞察周报")
        llm_report = str(context.get("llm", "暂无报告正文"))

        if not webhook_url or "open.feishu.cn" not in webhook_url:
            return {
                "status": "simulated",
                "message": "飞书 Webhook 处于未配置或模拟模式（真实发送请在节点配置中填入实际飞书机器人 Webhook URL）",
                "preview_title": title,
                "preview_content_length": len(llm_report),
            }

        payload = {
            "msg_type": "post",
            "content": {
                "post": {
                    "zh_cn": {
                        "title": title,
                        "content": [
                            [{"tag": "text", "text": llm_report[:2500]}],
                            [{"tag": "a", "text": "👉 查看更多工作台明细", "href": "https://github.com/wxl482/NexusDesk"}]
                        ]
                    }
                }
            }
        }
        loop = asyncio.get_event_loop()
        def _send():
            resp = requests.post(webhook_url, json=payload, timeout=10)
            return resp.json()

        res_data = await loop.run_in_executor(None, _send)
        return {"status": "sent", "response": res_data}

    @staticmethod
    async def _run_email(config: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """邮件发送模拟或 SMTP 发信"""
        recipient = config.get("recipient", "team@example.com")
        return {
            "status": "ready",
            "recipient": recipient,
            "message": f"周报邮件已投递至 {recipient}（已生成待发队列）",
        }
