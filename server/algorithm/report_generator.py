# -*- coding: utf-8 -*-
"""
综合报告生成模块 (report_generator.py)
========================================
Sprint 2 新增模块 —— 算法工程师 王顺凯

功能:
-----
1. **异常排序与优先级排序 (US-06)**
   按异常严重程度和出现频次对问题路径排序，帮助产品经理优先处理
   影响最大的体验问题。

2. **点击热度与停留时长聚合 (US-07)**
   为每个旅程图节点计算点击热度、停留时长等指标，生成热力数据，
   供前端看板直接渲染。

3. **综合分析报告生成**
   将路径图、异常检测、行为语义分析的结果汇总为结构化 JSON 报告，
   包含全局指标、节点级指标、异常排行和改进建议。

技术原理:
---------
- **加权评分**: 结合异常严重程度权重 (critical=4, high=3, medium=2, low=1)
  和出现频次计算优先级评分: priority = severity_weight × frequency
- **热度归一化**: 使用 min-max 归一化将点击次数映射到 [0, 1] 区间
- **停留时长分位数**: 使用中位数和 P90 判定是否异常

"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Optional

_UTC = timezone.utc

logger = logging.getLogger(__name__)

# 严重度权重映射
SEVERITY_WEIGHT = {
    "critical": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
}


class ReportGenerator:
    """
    综合分析报告生成器。

    使用方式:
    ---------
    >>> generator = ReportGenerator()
    >>> report = generator.generate(events, path_graph, anomaly_report)
    >>> print(report["ranked_anomalies"])
    >>> print(report["node_heatmap"])
    """

    def generate(
        self,
        events: list[dict[str, Any]],
        path_graph: Optional[dict[str, Any]] = None,
        anomaly_report: Optional[dict[str, Any]] = None,
        behavior_summary: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        生成综合分析报告。

        Parameters
        ----------
        events : list[dict]
            原始行为事件列表
        path_graph : dict, optional
            PathVectorizer 生成的路径图
        anomaly_report : dict, optional
            AnomalyDetector 生成的异常检测报告
        behavior_summary : dict, optional
            BehaviorSummarizer 生成的语义摘要

        Returns
        -------
        dict
            综合报告，包含:
            - global_metrics: 全局统计指标
            - node_heatmap: 节点级热力数据 (US-07)
            - ranked_anomalies: 按优先级排序的异常列表 (US-06)
            - improvement_suggestions: 改进建议
            - report_metadata: 报告元数据
        """
        # 1. 全局指标
        global_metrics = self._compute_global_metrics(events, path_graph, anomaly_report)

        # 2. 节点热力数据 (US-07)
        node_heatmap = self._compute_node_heatmap(events, path_graph)

        # 3. 异常排序 (US-06)
        ranked_anomalies = self._rank_anomalies(anomaly_report)

        # 4. 改进建议
        suggestions = self._generate_suggestions(ranked_anomalies, node_heatmap)

        report = {
            "global_metrics": global_metrics,
            "node_heatmap": node_heatmap,
            "ranked_anomalies": ranked_anomalies,
            "improvement_suggestions": suggestions,
            "behavior_summary": behavior_summary,
            "report_metadata": {
                "generated_at": datetime.now(tz=_UTC).isoformat(),
                "event_count": len(events),
                "sprint": "Sprint 2",
                "generator_version": "1.0.0",
            },
        }

        logger.info(
            "综合报告生成完成: %d 事件, %d 异常, %d 节点热力",
            len(events), len(ranked_anomalies), len(node_heatmap),
        )
        return report

    # ----------------------------------------------------------
    # US-07: 节点热力数据
    # ----------------------------------------------------------

    def _compute_node_heatmap(
        self,
        events: list[dict[str, Any]],
        path_graph: Optional[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        计算每个节点的点击热度与停留时长指标。

        算法:
        1. 遍历事件，按页面分组统计点击次数和停留时长
        2. 使用 min-max 归一化生成热度值 [0, 1]
        3. 合并路径图中的节点信息

        Returns
        -------
        list[dict]
            每个节点的热力数据:
            - node_id, page_url, label
            - click_count: 点击总次数
            - click_heat: 归一化热度 [0, 1]
            - total_dwell_ms: 总停留时长
            - avg_dwell_ms: 平均停留时长
            - visit_count: 访问次数
            - heat_level: "hot" / "warm" / "cool" / "cold"
        """
        # 按页面统计事件
        page_stats: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"click_count": 0, "total_dwell_ms": 0.0, "visit_count": 0, "events": []}
        )

        for e in events:
            route = e.get("route", e.get("page_url", "/unknown"))
            event_type = e.get("event_type", e.get("eventType", ""))

            if event_type in ("pointer_move", "scroll"):
                continue

            stats = page_stats[route]
            stats["visit_count"] += 1

            if event_type == "click":
                stats["click_count"] += 1

            duration = e.get("duration_ms", e.get("durationMs"))
            if duration is not None:
                stats["total_dwell_ms"] += float(duration)

        if not page_stats:
            return []

        # min-max 归一化点击热度
        click_counts = [s["click_count"] for s in page_stats.values()]
        max_clicks = max(click_counts) if click_counts else 1
        min_clicks = min(click_counts) if click_counts else 0
        click_range = max(max_clicks - min_clicks, 1)

        # 从路径图获取节点信息
        node_info = {}
        if path_graph:
            for node in path_graph.get("nodes", []):
                node_info[node.get("page_url", "")] = node

        heatmap = []
        for route, stats in page_stats.items():
            click_heat = (stats["click_count"] - min_clicks) / click_range
            avg_dwell = stats["total_dwell_ms"] / max(stats["visit_count"], 1)

            # 热度等级判定
            if click_heat >= 0.75:
                heat_level = "hot"
            elif click_heat >= 0.5:
                heat_level = "warm"
            elif click_heat >= 0.25:
                heat_level = "cool"
            else:
                heat_level = "cold"

            node = node_info.get(route, {})
            heatmap.append({
                "node_id": node.get("id", route),
                "page_url": route,
                "label": node.get("label", route),
                "click_count": stats["click_count"],
                "click_heat": round(click_heat, 3),
                "total_dwell_ms": round(stats["total_dwell_ms"], 1),
                "avg_dwell_ms": round(avg_dwell, 1),
                "visit_count": stats["visit_count"],
                "heat_level": heat_level,
            })

        # 按热度降序排列
        heatmap.sort(key=lambda x: x["click_heat"], reverse=True)
        return heatmap

    # ----------------------------------------------------------
    # US-06: 异常优先级排序
    # ----------------------------------------------------------

    def _rank_anomalies(
        self,
        anomaly_report: Optional[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        按严重程度和出现频次对异常排序。

        算法:
        - priority_score = severity_weight × frequency_factor
        - frequency_factor 基于同类异常的出现次数
        - 按 priority_score 降序排列

        Returns
        -------
        list[dict]
            排序后的异常列表，每项增加:
            - rank: 排名 (从 1 开始)
            - priority_score: 优先级评分
        """
        if not anomaly_report:
            return []

        anomalies = anomaly_report.get("anomalies", [])
        if not anomalies:
            return []

        # 统计同类异常频次
        type_counts = Counter(a.get("anomaly_type", "unknown") for a in anomalies)

        # 计算优先级评分
        scored = []
        for a in anomalies:
            severity = a.get("severity", "low")
            anomaly_type = a.get("anomaly_type", "unknown")

            weight = SEVERITY_WEIGHT.get(severity, 1)
            frequency = type_counts.get(anomaly_type, 1)

            # 综合评分: 严重度权重 × 频次因子
            priority_score = weight * (1 + 0.3 * (frequency - 1))

            scored.append({
                **a,
                "priority_score": round(priority_score, 2),
            })

        # 按优先级降序
        scored.sort(key=lambda x: x["priority_score"], reverse=True)

        # 添加排名
        for i, item in enumerate(scored, 1):
            item["rank"] = i

        return scored

    # ----------------------------------------------------------
    # 全局指标
    # ----------------------------------------------------------

    def _compute_global_metrics(
        self,
        events: list[dict[str, Any]],
        path_graph: Optional[dict[str, Any]],
        anomaly_report: Optional[dict[str, Any]],
    ) -> dict[str, Any]:
        """计算全局统计指标"""
        # 事件类型分布
        event_types = Counter(
            e.get("event_type", e.get("eventType", "unknown"))
            for e in events
        )

        # 唯一页面数
        unique_routes = set()
        for e in events:
            route = e.get("route", e.get("page_url"))
            if route:
                unique_routes.add(route)

        # 总停留时长
        total_dwell = sum(
            float(e.get("duration_ms", e.get("durationMs", 0)) or 0)
            for e in events
        )

        metrics = {
            "total_events": len(events),
            "unique_pages": len(unique_routes),
            "total_dwell_ms": round(total_dwell, 1),
            "event_type_distribution": dict(event_types),
        }

        if path_graph:
            meta = path_graph.get("metadata", {})
            metrics["node_count"] = meta.get("node_count", 0)
            metrics["edge_count"] = meta.get("edge_count", 0)
            metrics["total_duration_ms"] = meta.get("total_duration_ms", 0)

        if anomaly_report:
            metrics["total_anomalies"] = anomaly_report.get("total_anomalies", 0)
            metrics["health_score"] = anomaly_report.get("overall_health_score", 100)

        return metrics

    # ----------------------------------------------------------
    # 改进建议生成
    # ----------------------------------------------------------

    @staticmethod
    def _generate_suggestions(
        ranked_anomalies: list[dict[str, Any]],
        node_heatmap: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        基于异常排名和热力数据生成改进建议。
        """
        suggestions = []

        # 基于异常生成建议
        for anomaly in ranked_anomalies[:5]:  # 只取 Top 5
            suggestion = {
                "priority": anomaly.get("rank", 0),
                "category": anomaly.get("anomaly_type", "unknown"),
                "target_page": anomaly.get("page_url", ""),
                "description": anomaly.get("suggestion", anomaly.get("description", "")),
                "severity": anomaly.get("severity", "low"),
            }
            suggestions.append(suggestion)

        # 基于热力数据: 高热度 + 高停留 = 潜在问题页面
        for node in node_heatmap:
            if node["heat_level"] == "hot" and node["avg_dwell_ms"] > 10000:
                suggestions.append({
                    "priority": len(suggestions) + 1,
                    "category": "high_engagement_concern",
                    "target_page": node["page_url"],
                    "description": (
                        f"页面 [{node['label']}] 点击热度高 ({node['click_count']} 次) "
                        f"且平均停留时长 {node['avg_dwell_ms']:.0f}ms，"
                        "建议检查页面信息是否过于复杂或操作引导是否清晰。"
                    ),
                    "severity": "medium",
                })

        return suggestions
