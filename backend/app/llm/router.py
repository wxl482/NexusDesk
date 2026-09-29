import re
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class ModelRouter:
    """
    【P0 工业级智能模型动态路由分流器】
    根据用户输入的意图特征、代码密度、推理复杂度与上下文长度，
    自适应路由至「极速响应模型 (Fast Tier)」或「高阶深度思考/推理模型 (Reasoning Tier)」，
    兼顾秒级首字延迟、高难度逻辑准确度与使用成本。
    """

    FAST_MODEL = "deepseek-chat"
    REASONING_MODEL = "deepseek-reasoner"

    # 高推理复杂度特征词库
    REASONING_KEYWORDS = [
        "推导", "数学证明", "逻辑推理", "算法分析", "复杂度", "递归",
        "动态规划", "系统架构", "并发锁", "死锁分析", "排查bug", "traceback",
        "debug", "性能瓶颈", "逆向", "博弈", "底层原理", "详细解释为什么",
        "深度思考", "多角度对比", "设计模式", "重构方案", "proof", "derivation"
    ]

    # 代码密集度正则
    CODE_PATTERNS = [
        r"```[a-zA-Z]*\n",
        r"\bdef\s+[a-zA-Z_]\w*\s*\(",
        r"\bclass\s+[a-zA-Z_]\w*",
        r"\bfunction\s+[a-zA-Z_]\w*",
        r"\bimport\s+[\w\.]+",
        r"\bfrom\s+[\w\.]+\s+import",
        r"\bSELECT\s+.+\s+FROM\b",
        r"\{\s*[\"']?[a-zA-Z0-9_-]+[\"']?\s*:",
    ]

    @classmethod
    def route_prompt(cls, prompt: str, current_model: Optional[str] = None) -> Dict[str, Any]:
        """
        分析提示词并返回自适应调度推荐
        """
        # 若用户手动固定指定了非 auto 模型，则尊重用户的强制选择
        if current_model and current_model not in ["auto", "smart", "default", ""]:
            return {
                "model": current_model,
                "tier": "custom",
                "reason": "用户显式指定模型，保持原有设定。",
            }

        text = prompt.strip().lower()
        if not text:
            return {
                "model": cls.FAST_MODEL,
                "tier": "fast",
                "reason": "输入为空，使用极速模型兜底。",
            }

        score = 0
        reasons = []

        # 1. 关键词命中加权
        for kw in cls.REASONING_KEYWORDS:
            if kw in text:
                score += 2
                reasons.append(f"命中高阶推理特征词「{kw}」")
                break

        # 2. 代码密集度加权
        code_hits = sum(1 for pattern in cls.CODE_PATTERNS if re.search(pattern, prompt, re.IGNORECASE))
        if code_hits >= 1:
            score += 3
            reasons.append(f"检测到高密度代码语法结构 ({code_hits} 处命中)")

        # 3. 文本长度加权
        if len(prompt) > 300:
            score += 1
            reasons.append("输入文本较长，可能包含复杂长上下文分析需求")

        # 决策阈值
        if score >= 2:
            selected_model = cls.REASONING_MODEL
            tier = "reasoning"
            decision_reason = "检测为高阶编码或多步逻辑推理需求，自动调度深度思考推理模型。"
        else:
            selected_model = cls.FAST_MODEL
            tier = "fast"
            decision_reason = "检测为常规日常问答、文字撰写或快速查询，自动调度极速模型以降低延迟。"

        logger.info(f"[ModelRouter] 意图分流结果: {tier} -> {selected_model} (得分: {score}, 理由: {decision_reason})")
        return {
            "model": selected_model,
            "tier": tier,
            "score": score,
            "reason": decision_reason,
            "details": reasons,
        }
