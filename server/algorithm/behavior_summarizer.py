# -*- coding: utf-8 -*-
"""
LLM 行为语义转换模块 (behavior_summarizer.py)
===============================================
利用大语言模型 (GPT-4o-mini) 将用户操作序列转化为
自然语言行为描述，包括用户意图推断、痛点识别、效率评估等。

技术原理:
---------
1. **输入**: 用户操作事件序列 + 路径图摘要
2. **Prompt Engineering**: 使用精心设计的多场景 Prompt 模板，
   引导 LLM 分析行为数据并输出结构化 JSON 结果
3. **输出**: BehaviorSummary（意图、叙述、痛点、建议）

设计方法:
---------
- 采用 Structured Output + 少样本学习 (Few-shot) 策略
- 按业务场景 (电商支付、注册、浏览) 切换不同 Prompt 模板
- 输出强制 JSON 格式，便于下游消费

"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ============================================================
# Prompt 模板库 —— 分场景引导 LLM 分析
# ============================================================

# 通用行为分析 Prompt
GENERAL_BEHAVIOR_PROMPT = """你是一位资深的 UX 数据分析师。请分析以下用户行为日志，输出结构化的行为语义摘要。

## 行为日志数据
{event_data}

## 路径摘要
{path_summary}

## 分析任务
请根据上述数据，从以下维度进行分析：

1. **user_intent** (用户意图): 推断用户最可能的目标是什么
2. **behavior_narrative** (行为叙述): 用2-3句自然语言描述用户的操作过程
3. **pain_points** (痛点): 列出用户可能遇到的困难或不便，每条 ≤ 30 字
4. **intent_labels** (意图标签): 给出 2-5 个意图关键词标签
5. **efficiency_rating** (效率评级): 从 "efficient" / "moderate" / "inefficient" 中选择
6. **recommendations** (改进建议): 给出 2-3 条具体的 UX 优化建议

## 输出格式
请以严格 JSON 返回：
```json
{{
  "user_intent": "...",
  "behavior_narrative": "...",
  "pain_points": ["...", "..."],
  "intent_labels": ["...", "..."],
  "efficiency_rating": "efficient|moderate|inefficient",
  "recommendations": ["...", "..."]
}}
```

## 注意事项
- 只输出 JSON，不附加其他文字
- 使用中文描述
- 痛点和建议要具体可操作"""


# 电商结算场景专用 Prompt
CHECKOUT_BEHAVIOR_PROMPT = """你是一位电商 UX 分析专家。请分析以下用户在购物/结算流程中的行为日志。

## 行为日志数据
{event_data}

## 路径摘要
{path_summary}

## 重点关注
- 用户是否在支付页面反复犹豫
- 优惠券/折扣码使用是否顺畅
- 页面跳转是否合理（有无不必要的回退）
- 表单填写流畅度

## 输出格式
请以严格 JSON 返回：
```json
{{
  "user_intent": "...",
  "behavior_narrative": "...",
  "pain_points": ["...", "..."],
  "intent_labels": ["...", "..."],
  "efficiency_rating": "efficient|moderate|inefficient",
  "recommendations": ["...", "..."],
  "checkout_insights": {{
    "hesitation_detected": true/false,
    "coupon_friction": true/false,
    "unnecessary_backtracking": true/false,
    "estimated_conversion_risk": "low|medium|high"
  }}
}}
```

只输出 JSON，使用中文描述。"""


# 注册/登录场景专用 Prompt
AUTH_BEHAVIOR_PROMPT = """你是一位用户增长分析专家。请分析以下用户在注册/登录流程中的行为日志。

## 行为日志数据
{event_data}

## 路径摘要
{path_summary}

## 重点关注
- 注册步骤是否过多
- 表单字段是否造成用户流失
- 验证码/安全验证是否顺畅
- 是否存在放弃注册并离开的信号

## 输出格式
请以严格 JSON 返回：
```json
{{
  "user_intent": "...",
  "behavior_narrative": "...",
  "pain_points": ["...", "..."],
  "intent_labels": ["...", "..."],
  "efficiency_rating": "efficient|moderate|inefficient",
  "recommendations": ["...", "..."]
}}
```

只输出 JSON，使用中文描述。"""


# 浏览/探索场景专用 Prompt
BROWSE_BEHAVIOR_PROMPT = """你是一位内容运营分析专家。请分析以下用户的浏览探索行为日志。

## 行为日志数据
{event_data}

## 路径摘要
{path_summary}

## 重点关注
- 用户是否有明确的浏览目的
- 页面停留时间分布是否合理
- 内容发现效率（是否频繁搜索/筛选）
- 是否存在"迷失"行为（反复跳转无目的）

## 输出格式
```json
{{
  "user_intent": "...",
  "behavior_narrative": "...",
  "pain_points": ["...", "..."],
  "intent_labels": ["...", "..."],
  "efficiency_rating": "efficient|moderate|inefficient",
  "recommendations": ["...", "..."]
}}
```

只输出 JSON，使用中文描述。"""


# 场景 → Prompt 映射
SCENARIO_PROMPTS: dict[str, str] = {
    "general": GENERAL_BEHAVIOR_PROMPT,
    "checkout": CHECKOUT_BEHAVIOR_PROMPT,
    "auth": AUTH_BEHAVIOR_PROMPT,
    "browse": BROWSE_BEHAVIOR_PROMPT,
}

# 自动场景识别的路由关键词
SCENARIO_KEYWORDS: dict[str, list[str]] = {
    "checkout": ["cart", "checkout", "payment", "pay", "order", "confirm", "coupon"],
    "auth": ["login", "register", "signup", "signin", "password", "verify", "auth"],
    "browse": ["search", "browse", "explore", "category", "product", "list", "home"],
}


# ============================================================
# BehaviorSummarizer 类
# ============================================================


class BehaviorSummarizer:
    """
    基于 LLM 的行为语义转换器。

    使用方式:
    ---------
    >>> summarizer = BehaviorSummarizer(api_key="sk-xxx")
    >>> result = await summarizer.summarize(events, path_graph)
    >>> print(result["user_intent"])
    >>> print(result["pain_points"])
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-4o-mini",
    ) -> None:
        self.api_key = api_key or os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY", "")
        self.model = model
        self._client = None

    def _get_client(self):
        """延迟初始化 OpenAI 客户端"""
        if self._client is None:
            try:
                from openai import AsyncOpenAI
                self._client = AsyncOpenAI(api_key=self.api_key)
            except ImportError:
                raise RuntimeError("依赖 openai 包，请运行: pip install openai>=1.14.0")
        return self._client

    # ----------------------------------------------------------
    # 核心方法
    # ----------------------------------------------------------

    async def summarize(
        self,
        events: list[dict[str, Any]],
        path_graph: Optional[dict[str, Any]] = None,
        scenario: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        对用户行为序列进行语义化分析。

        Parameters
        ----------
        events : list[dict]
            用户操作事件列表
        path_graph : dict, optional
            由 PathVectorizer 生成的路径图数据
        scenario : str, optional
            业务场景 ("checkout", "auth", "browse", "general")
            若不指定则自动识别

        Returns
        -------
        dict
            语义化分析结果，结构同 Prompt 模板中的 JSON 定义
        """
        # 自动识别场景
        if scenario is None:
            scenario = self._detect_scenario(events)

        # 准备输入数据
        event_data = self._format_events(events)
        path_summary = self._format_path_summary(path_graph) if path_graph else "无路径图数据"

        # 选择 Prompt 模板
        prompt_template = SCENARIO_PROMPTS.get(scenario, GENERAL_BEHAVIOR_PROMPT)
        prompt = prompt_template.format(
            event_data=event_data,
            path_summary=path_summary,
        )

        # 调用 LLM
        client = self._get_client()

        try:
            response = await client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "你是一位资深的用户体验数据分析师。"
                                   "请基于用户行为日志进行深入分析，"
                                   "输出结构化的 JSON 结果。只输出 JSON。",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=2048,
                temperature=0.3,
            )

            raw_text = response.choices[0].message.content or "{}"
            result = self._parse_response(raw_text)
            result["scenario"] = scenario

            logger.info(
                "行为语义化完成: scenario=%s, intent=%s, rating=%s",
                scenario,
                result.get("user_intent", "N/A"),
                result.get("efficiency_rating", "N/A"),
            )
            return result

        except Exception as exc:
            logger.error("LLM API 调用失败: %s", exc)
            raise

    async def summarize_batch(
        self,
        sessions: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        批量分析多个用户会话。

        Parameters
        ----------
        sessions : list[dict]
            每个元素包含 {"events": [...], "path_graph": {...}}

        Returns
        -------
        list[dict]
            每个会话的语义化分析结果
        """
        import asyncio

        tasks = [
            self.summarize(
                s.get("events", []),
                s.get("path_graph"),
                s.get("scenario"),
            )
            for s in sessions
        ]
        return await asyncio.gather(*tasks)

    # ----------------------------------------------------------
    # 场景自动识别
    # ----------------------------------------------------------

    @staticmethod
    def _detect_scenario(events: list[dict[str, Any]]) -> str:
        """根据事件中的路由关键词自动判断业务场景"""
        routes = set()
        for event in events:
            route = event.get("route", event.get("page_url", ""))
            routes.add(route.lower())

        route_text = " ".join(routes)

        # 计算每个场景的匹配分数
        scores: dict[str, int] = {}
        for scenario, keywords in SCENARIO_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in route_text)
            scores[scenario] = score

        # 返回最高分的场景
        best = max(scores, key=scores.get)  # type: ignore
        if scores[best] == 0:
            return "general"
        return best

    # ----------------------------------------------------------
    # 数据格式化
    # ----------------------------------------------------------

    @staticmethod
    def _format_events(events: list[dict[str, Any]], max_events: int = 30) -> str:
        """将事件列表转为 LLM 可读的文本摘要"""
        # 限制事件数量，避免超出 token 限制
        trimmed = events[:max_events]

        lines = []
        for i, e in enumerate(trimmed, 1):
            event_type = e.get("event_type", e.get("eventType", "?"))
            route = e.get("route", e.get("page_url", "?"))
            ts = e.get("timestamp", "?")
            elem = e.get("element_id", e.get("elementId", ""))
            intent = e.get("intent_label", e.get("intentLabel", ""))
            duration = e.get("duration_ms", e.get("durationMs", ""))

            line = f"[{i}] {ts} | {event_type} | 页面: {route}"
            if elem:
                line += f" | 元素: {elem}"
            if intent:
                line += f" | 意图: {intent}"
            if duration:
                line += f" | 停留: {duration}ms"
            lines.append(line)

        if len(events) > max_events:
            lines.append(f"... (共 {len(events)} 条，已截取前 {max_events} 条)")

        return "\n".join(lines)

    @staticmethod
    def _format_path_summary(path_graph: dict[str, Any]) -> str:
        """将路径图数据格式化为 LLM 可读的摘要"""
        nodes = path_graph.get("nodes", [])
        edges = path_graph.get("edges", [])
        meta = path_graph.get("metadata", {})

        lines = [
            f"路径图概况: {meta.get('node_count', len(nodes))} 个页面, "
            f"{meta.get('edge_count', len(edges))} 条转换, "
            f"总时长 {meta.get('total_duration_ms', 0):.0f}ms",
            "",
            "页面节点:",
        ]

        for n in nodes:
            label = n.get("label", n.get("page_url", "?"))
            visits = n.get("visit_count", 0)
            dwell = n.get("avg_dwell_ms", 0)
            lines.append(f"  - {label}: 访问 {visits} 次, 平均停留 {dwell:.0f}ms")

        lines.append("")
        lines.append("转换边:")
        for e in edges:
            src = e.get("source", "?")
            tgt = e.get("target", "?")
            count = e.get("transition_count", 0)
            lines.append(f"  - {src} → {tgt}: {count} 次")

        return "\n".join(lines)

    # ----------------------------------------------------------
    # 响应解析
    # ----------------------------------------------------------

    @staticmethod
    def _parse_response(raw_text: str) -> dict[str, Any]:
        """解析 LLM 响应中的 JSON"""
        text = raw_text.strip()

        # 直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 提取代码块
        if "```" in text:
            start = text.find("```json")
            if start == -1:
                start = text.find("```")
            if start != -1:
                start = text.index("\n", start) + 1
                end = text.find("```", start)
                if end != -1:
                    try:
                        return json.loads(text[start:end].strip())
                    except json.JSONDecodeError:
                        pass

        # 提取花括号
        first_brace = text.find("{")
        last_brace = text.rfind("}")
        if first_brace != -1 and last_brace > first_brace:
            try:
                return json.loads(text[first_brace:last_brace + 1])
            except json.JSONDecodeError:
                pass

        logger.warning("无法解析 LLM 返回: %s", text[:200])
        return {
            "user_intent": "解析失败",
            "behavior_narrative": raw_text[:500],
            "pain_points": [],
            "intent_labels": [],
            "efficiency_rating": "unknown",
            "recommendations": [],
        }
