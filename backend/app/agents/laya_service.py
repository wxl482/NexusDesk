import os
import time
import logging
import threading
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# 修正 macOS / requests 下 NO_PROXY 包含 ::1 导致解析端口报错的问题
if "NO_PROXY" in os.environ and "::1" in os.environ["NO_PROXY"]:
    os.environ["NO_PROXY"] = os.environ["NO_PROXY"].replace("::1/128", "").replace("::1", "")
if "no_proxy" in os.environ and "::1" in os.environ["no_proxy"]:
    os.environ["no_proxy"] = os.environ["no_proxy"].replace("::1/128", "").replace("::1", "")

# 默认启用高性能 Hugging Face 镜像加速，确保国内云服务器部署时不卡死在模型权重下载
if "HF_ENDPOINT" not in os.environ:
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"


class LayaDecisionService:
    """
    基于 NandhaKishorM/laya 构建的系统 1 (System 1) 毫秒级决策引擎服务。
    
    架构特性：
    1. 非自回归单次前向推理：无需逐 Token 解码，决策延迟稳定在 20ms ~ 40ms；
    2. 多智能体动态分流 (Multi-Agent Routing)：自动识别任务意图并分发到对应专项 Agent；
    3. 工具调用先验门禁 (Tool Gating)：毫秒级判断是否需要调用外部工具；
    4. 智能审批高危审计 (Smart Approval Guardrail)：对终端命令和写操作进行毫秒级风险评分；
    5. 智能常驻内存池 (Memory Pool)：max_loaded=3 保持中文与英文检查点常驻，避免二次加载开销。
    """
    _instance: Optional["LayaDecisionService"] = None

    def __init__(self):
        self._router = None
        self._initialized = False
        self._init_error = None
        self._lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "LayaDecisionService":
        if cls._instance is None:
            cls._instance = LayaDecisionService()
        return cls._instance

    def _ensure_router(self):
        """线程安全地加载 Laya 路由器单例并保持检查点常驻"""
        if self._initialized and self._router is not None:
            return self._router

        with self._lock:
            if self._initialized and self._router is not None:
                return self._router

            try:
                from laya import Router
                logger.info("⚡ [Laya] 正在启动 System 1 决策路由器 (Device: cpu, max_loaded=3)...")
                # max_loaded=3 确保 english 和 multilingual 检查点均常驻内存，推理仅需 25ms~35ms
                self._router = Router(device="cpu", max_loaded=3)
                self._initialized = True
                logger.info("✅ [Laya] 决策路由器就绪！")
            except Exception as e:
                self._init_error = str(e)
                logger.warning(f"⚠️ [Laya] 路由器加载失败，将启用规则兜底: {e}")
                self._router = None
                self._initialized = False

        return self._router

    def warmup(self):
        """后台异步预热，使第一次请求也享受 ~30ms 极速响应"""
        def _warmup_worker():
            try:
                router = self._ensure_router()
                if router:
                    logger.info("⚡ [Laya] 正在预热决策引擎检查点...")
                    router.predict("你好", {"warmup": {"type": "noul", "instructions": "greeting?"}})
                    logger.info("✅ [Laya] 预热完成，已进入全速决策状态！")
            except Exception as e:
                logger.warning(f"[Laya] 预热偶发提示: {e}")

        t = threading.Thread(target=_warmup_worker, daemon=True)
        t.start()

    def predict_intent_and_agent(self, text: str) -> Dict[str, Any]:
        """
        对用户提问进行毫秒级意图识别、Agent 派发与工具门禁决策。
        
        返回字段包含：
        - agent: 'coder' | 'researcher' | 'terminal' | 'rag' | 'chat'
        - agent_name: 中文名
        - confidence: 判定置信度
        - needs_tool: 是否需要调用外部工具
        - risk_score: 潜在高危程度 (0.0 ~ 1.0)
        - latency_ms: 推理耗时 (毫秒)
        """
        text_clean = (text or "").strip()
        if not text_clean:
            return {
                "agent": "chat",
                "agent_name": "日常对话",
                "confidence": 1.0,
                "probabilities": {"chat": 1.0},
                "needs_tool": False,
                "needs_tool_prob": 0.0,
                "risk_score": 0.0,
                "is_high_risk": False,
                "latency_ms": 0.1,
                "is_fallback": True,
            }

        router = self._ensure_router()
        if router is None:
            return self._fallback_rule_decision(text_clean)

        # 常见强特征词与本地知识库文档命中快速先验检测
        lower_t = text_clean.lower()
        has_chat_hint = any(k in lower_t for k in ["你好", "您好", "hi", "hello", "早安", "晚安", "介绍一下你自己", "你是谁", "介绍自己", "自我介绍", "谢谢", "再见", "聊聊", "是谁"])
        has_search_hint = any(k in lower_t for k in ["搜索", "检索", "查一下", "最新", "前沿", "动态", "突破", "新闻", "2025", "简报", "调研", "上网查", "抓取"])
        has_code_hint = any(k in lower_t for k in ["写代码", "编写代码", "实现", "函数", "算法", "bug", "脚本", "python", "javascript", "vue", "java", "c++", "报错"])
        has_term_hint = any(k in lower_t for k in ["执行命令", "终端", "shell", "bash", "git", "删除文件", "查看目录", "ls", "cd", "mkdir"])
        has_rag_hint = any(k in lower_t for k in ["知识库", "上传的文档", "查阅文档", "公司资料", "手册"])

        # 检查是否直接命中了本地知识库已录入的文档标题关键词
        try:
            from app.rag.knowledge_catalog import check_knowledge_base_hit
            matched_kb_docs = check_knowledge_base_hit(lower_t)
        except Exception:
            matched_kb_docs = None

        if matched_kb_docs:
            has_rag_hint = True
            logger.info(f"⚡ [Laya] 用户提问命中本地知识库文档: {matched_kb_docs}，毫秒级快速分流至 RAG 专家。")
            return {
                "agent": "rag",
                "agent_name": "私有知识库专家",
                "confidence": 0.98,
                "probabilities": {"rag": 0.98, "chat": 0.0, "coder": 0.01, "researcher": 0.01, "terminal": 0.0},
                "needs_tool": True,
                "needs_tool_prob": 0.98,
                "risk_score": 0.0,
                "is_high_risk": False,
                "latency_ms": 0.3,
                "model_used": "kb_hit_fastpath",
                "matched_documents": matched_kb_docs,
                "is_fallback": False,
            }

        # 针对极为明确的日常问候/自我介绍，直接毫秒级短路，零开销返回纯对话
        if has_chat_hint and not (has_search_hint or has_term_hint or has_rag_hint or has_code_hint):
            return {
                "agent": "chat",
                "agent_name": "日常对话",
                "confidence": 0.99,
                "probabilities": {"chat": 0.99, "coder": 0.0, "researcher": 0.0, "terminal": 0.0, "rag": 0.0},
                "needs_tool": False,
                "needs_tool_prob": 0.0,
                "risk_score": 0.0,
                "is_high_risk": False,
                "latency_ms": 0.2,
                "model_used": "rule_fastpath",
                "is_fallback": False,
            }

        questions = {
            "agent": {
                "type": "choice",
                "instructions": "Which specialized agent should handle this user request?",
                "criteria": {
                    "coder": "writing code, programming, algorithms, scripting, debugging, fixing syntax, python js java c++ web development, 编写代码, 算法实现, 编写脚本, 修复Bug, 编程问题",
                    "researcher": "web searching, internet lookup, real-time facts, news, documentation retrieval, date weather inquiry, latest advances, breakthroughs, industry trends, 搜索互联网, 检索最新前沿突破, 查阅行业动态, 查询天气, 查询最新新闻, 查找资料, 时效信息检索, 检索, 调研, 简报",
                    "terminal": "running shell commands, terminal execution, system administration, git operations, file deletion, directory management, 执行终端命令, Linux/Mac Shell指令, Git操作, 文件管理, 系统监控",
                    "rag": "querying private internal knowledge base, searching uploaded enterprise documents, proprietary manuals, 查询本地知识库, 检索上传的文档, 查阅私有资料, 手册问答",
                    "chat": "casual conversation, greetings, say hello, introduction, who are you, identity inquiry, simple Q&A, general chat, 打招呼, 问好, 礼貌闲聊, 询问你是谁, 身份介绍, 日常对话, 通用简答",
                },
            },
            "needs_tool": {
                "type": "noul",
                "instructions": "Does this request require executing external tools, web searches, searching latest internet facts, running shell commands, or accessing local disk files?",
            },
            "risk": {
                "type": "noul",
                "instructions": "Does this request contain potentially destructive or irreversible actions like deleting files, formatting, or altering system files?",
            },
        }

        try:
            t0 = time.time()
            res = router.predict(text_clean, questions)
            latency_ms = (time.time() - t0) * 1000

            agent_choice = res["answers"]["agent"]["choice"]
            agent_probs = res["answers"]["agent"]["probabilities"]
            confidence = float(agent_probs.get(agent_choice, 0.8))
            needs_tool_prob = float(res["answers"]["needs_tool"]["noul"])
            risk_score = float(res["answers"]["risk"]["noul"])

            # 语义纠偏：优先尊重明显的强特征意图，避免被过度平滑
            if has_search_hint and agent_choice != "researcher":
                if agent_probs.get("researcher", 0) > 0.15 or agent_choice in ["chat", "coder"]:
                    agent_choice = "researcher"
                    confidence = max(confidence, 0.82)
                    needs_tool_prob = max(needs_tool_prob, 0.85)
            elif has_rag_hint and agent_choice != "rag":
                agent_choice = "rag"
                confidence = max(confidence, 0.88)
                needs_tool_prob = max(needs_tool_prob, 0.90)
            elif has_term_hint and agent_choice != "terminal":
                agent_choice = "terminal"
                confidence = max(confidence, 0.88)
                needs_tool_prob = max(needs_tool_prob, 0.90)

            # 纯概念提问或原理探讨（如"为什么..."、"什么是..."），在无外部搜索/执行命令需求时直接走对话
            is_concept_query = any(lower_t.startswith(p) for p in ["为什么", "什么是", "如何看待", "怎么看待", "啥是", "解释一下", "谈谈"])
            if is_concept_query and not (has_search_hint or has_term_hint or has_rag_hint or has_code_hint):
                agent_choice = "chat"
                confidence = max(confidence, 0.85)

            # 仅在所有选项置信度极低（接近均匀随机 0.20）且无明显工具特征时才降级为 'chat'
            if confidence < 0.28 and not (has_search_hint or has_code_hint or has_term_hint or has_rag_hint):
                agent_choice = "chat"
                confidence = 0.85

            if has_search_hint or has_term_hint or has_rag_hint:
                needs_tool = True
            elif agent_choice == "chat":
                needs_tool = False
            else:
                needs_tool = needs_tool_prob >= 0.60

            agent_names = {
                "coder": "代码工程智能体",
                "researcher": "网络研报智能体",
                "terminal": "系统运维智能体",
                "rag": "私有知识库专家",
                "chat": "对话助手",
            }

            return {
                "agent": agent_choice,
                "agent_name": agent_names.get(agent_choice, agent_choice),
                "confidence": round(confidence, 4),
                "probabilities": {k: round(v, 4) for k, v in agent_probs.items()},
                "needs_tool": needs_tool,
                "needs_tool_prob": round(needs_tool_prob, 4),
                "risk_score": round(risk_score, 4),
                "is_high_risk": risk_score >= 0.65,
                "latency_ms": round(latency_ms, 1),
                "model_used": res.get("routing", {}).get("model", "multilingual"),
                "is_fallback": False,
            }
        except Exception as e:
            logger.error(f"[Laya] 推理异常: {e}")
            return self._fallback_rule_decision(text_clean)

    def audit_action_risk(self, action_name: str, target: str) -> Dict[str, Any]:
        """
        对即将执行的工具操作进行毫秒级安全风险评估（用于 Smart Approval 智能审批）。
        
        例如：
        - action_name: "execute_terminal_command", target: "rm -rf /tmp/data" -> 高危 (0.99)
        - action_name: "execute_terminal_command", target: "git status" -> 安全 (0.01)
        """
        router = self._ensure_router()
        text_to_audit = f"Action: {action_name}\nTarget/Command: {target}"

        # 明显的高危关键词极速短路拦截
        lower_target = target.lower()
        if any(kw in lower_target for kw in ["rm -rf", "mkfs", "dd if=", ":(){ :|:& };:", "drop database", "chmod 777 /"]):
            return {
                "risk_score": 0.99,
                "is_high_risk": True,
                "reason": "检测到已知极高危破坏性指令特征",
                "latency_ms": 0.1,
            }

        if router is None:
            return {
                "risk_score": 0.2,
                "is_high_risk": False,
                "reason": "规则默认放行",
                "latency_ms": 0.1,
            }

        questions = {
            "danger": {
                "type": "noul",
                "instructions": "Is this action dangerous, destructive, deleting data, terminating critical processes, or altering system files?",
            }
        }

        try:
            t0 = time.time()
            res = router.predict(text_to_audit, questions)
            latency_ms = (time.time() - t0) * 1000
            score = float(res["answers"]["danger"]["noul"])
            return {
                "risk_score": round(score, 4),
                "is_high_risk": score >= 0.6,
                "reason": "高风险破坏性行为" if score >= 0.6 else "属于常规只读/安全操作",
                "latency_ms": round(latency_ms, 1),
            }
        except Exception as e:
            logger.warning(f"[Laya] 风险审计异常: {e}")
            return {
                "risk_score": 0.3,
                "is_high_risk": False,
                "reason": "审计降级",
                "latency_ms": 0.1,
            }

    def _fallback_rule_decision(self, text: str) -> Dict[str, Any]:
        """降级兜底规则"""
        lower = text.lower()
        if any(w in lower for w in ["写代码", "python", "函数", "算法", "bug", "脚本", "class ", "def ", "实现"]):
            agent = "coder"
            agent_name = "代码工程智能体"
            needs_tool = False
        elif any(w in lower for w in ["搜索", "今天", "新闻", "天气", "查一下", "最新", "找找"]):
            agent = "researcher"
            agent_name = "网络研报智能体"
            needs_tool = True
        elif any(w in lower for w in ["终端", "执行", "命令", "git ", "ls", "cd ", "删除", "创建文件", "运行"]):
            agent = "terminal"
            agent_name = "系统运维智能体"
            needs_tool = True
        elif any(w in lower for w in ["知识库", "文档里", "根据文件", "手册", "参考文档"]):
            agent = "rag"
            agent_name = "私有知识库专家"
            needs_tool = True
        else:
            agent = "chat"
            agent_name = "对话助手"
            needs_tool = False

        return {
            "agent": agent,
            "agent_name": agent_name,
            "confidence": 0.8,
            "probabilities": {agent: 0.8},
            "needs_tool": needs_tool,
            "needs_tool_prob": 0.8 if needs_tool else 0.2,
            "risk_score": 0.1,
            "is_high_risk": False,
            "latency_ms": 0.5,
            "is_fallback": True,
        }


# 全局单例导出
laya_service = LayaDecisionService.get_instance()
# 启动时后台异步预热
laya_service.warmup()
