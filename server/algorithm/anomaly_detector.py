# -*- coding: utf-8 -*-
"""
异常检测模块 (anomaly_detector.py)
====================================
基于统计学方法对用户行为序列进行异常识别，涵盖：
1. 路径熵异常 —— 检测用户是否在页面间迷失/循环
2. 停留时间异常 —— 检测用户在某页面停留时间过长（犹豫）
3. 愤怒点击 —— 检测用户短时间内在同一元素上重复点击
4. 死胡同检测 —— 检测用户到达某页面后无法继续前进

技术原理:
---------
- **路径熵 (Shannon Entropy)**: 量化路径的随机程度
  - 低熵 = 路径规律有序（正常流程）
  - 高熵 = 路径混乱（用户困惑/迷失）
- **Z-Score / 固定阈值**: 结合统计偏差与经验阈值判定异常
- **滑动窗口**: 对愤怒点击使用时间窗口内的频率统计

"""

from __future__ import annotations

import logging
import math
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ============================================================
# 异常类型定义
# ============================================================

ANOMALY_TYPES = {
    "loop": "循环跳转异常",
    "long_dwell": "停留时间异常",
    "high_path_entropy": "路径熵异常（用户困惑）",
    "rage_click": "愤怒点击",
    "dead_end": "死胡同",
}

SEVERITY_LEVELS = ["low", "medium", "high", "critical"]


# ============================================================
# AnomalyDetector 类
# ============================================================


class AnomalyDetector:
    """
    用户行为异常检测器。

    使用方式:
    ---------
    >>> detector = AnomalyDetector()
    >>> report = detector.detect(events, path_graph)
    >>> print(report["anomalies"])
    >>> print(report["overall_health_score"])
    """

    def __init__(
        self,
        loop_threshold: int = 3,
        dwell_ms_threshold: float = 15000,
        entropy_threshold: float = 2.0,
        rage_click_window_ms: float = 3000,
        rage_click_count: int = 4,
    ) -> None:
        """
        Parameters
        ----------
        loop_threshold : int
            同一对页面之间来回跳转次数 ≥ 此值则视为循环异常
        dwell_ms_threshold : float
            页面停留时间 ≥ 此值（毫秒）视为异常停留
        entropy_threshold : float
            路径熵 ≥ 此值视为路径混乱
        rage_click_window_ms : float
            愤怒点击检测的时间窗口（毫秒）
        rage_click_count : int
            时间窗口内点击同一元素 ≥ 此次数视为愤怒点击
        """
        self.loop_threshold = loop_threshold
        self.dwell_ms_threshold = dwell_ms_threshold
        self.entropy_threshold = entropy_threshold
        self.rage_click_window_ms = rage_click_window_ms
        self.rage_click_count = rage_click_count

    # ----------------------------------------------------------
    # 综合检测入口
    # ----------------------------------------------------------

    def detect(
        self,
        events: list[dict[str, Any]],
        path_graph: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        对事件序列执行全面的异常检测。

        Parameters
        ----------
        events : list[dict]
            用户行为事件列表
        path_graph : dict, optional
            由 PathVectorizer 生成的路径图

        Returns
        -------
        dict
            异常检测报告，包含:
            - anomalies: 异常记录列表
            - overall_health_score: 健康度评分 (0-100)
            - summary: 文字总结
        """
        anomalies: list[dict[str, Any]] = []

        # 1. 循环跳转检测
        loop_results = self._detect_loops(events)
        anomalies.extend(loop_results)

        # 2. 停留时间异常检测
        dwell_results = self._detect_long_dwell(events)
        anomalies.extend(dwell_results)

        # 3. 路径熵检测
        entropy_results = self._detect_path_entropy(events)
        anomalies.extend(entropy_results)

        # 4. 愤怒点击检测
        rage_results = self._detect_rage_clicks(events)
        anomalies.extend(rage_results)

        # 5. 死胡同检测（需要路径图数据）
        if path_graph:
            dead_end_results = self._detect_dead_ends(events, path_graph)
            anomalies.extend(dead_end_results)

        # 计算健康度评分
        health_score = self._calculate_health_score(anomalies, len(events))

        # 生成总结
        summary = self._generate_summary(anomalies)

        report = {
            "total_anomalies": len(anomalies),
            "anomalies": anomalies,
            "overall_health_score": round(health_score, 1),
            "summary": summary,
            "metrics": {
                "loop_detected": any(a["anomaly_type"] == "loop" for a in anomalies),
                "dwell_anomaly": any(a["anomaly_type"] == "long_dwell" for a in anomalies),
                "high_entropy": any(a["anomaly_type"] == "high_path_entropy" for a in anomalies),
                "rage_clicks": any(a["anomaly_type"] == "rage_click" for a in anomalies),
            },
        }

        logger.info(
            "异常检测完成: %d 条异常, 健康度 %.1f/100",
            len(anomalies), health_score,
        )
        return report

    # ----------------------------------------------------------
    # 子检测器: 循环跳转
    # ----------------------------------------------------------

    def _detect_loops(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        检测页面间的循环跳转模式。
        
        算法: 统计相邻页面之间的双向转换次数，
        如果 A→B 和 B→A 的总次数 >= 阈值，则判定为循环。
        """
        routes = []
        for e in events:
            route = e.get("route", e.get("page_url", ""))
            event_type = e.get("event_type", e.get("eventType", ""))
            if route and event_type not in ("pointer_move", "scroll"):
                routes.append(route)

        if len(routes) < self.loop_threshold + 1:
            return []

        # 统计转换次数
        transitions: dict[tuple[str, str], int] = {}
        for prev_r, next_r in zip(routes, routes[1:]):
            if prev_r != next_r:
                key = (prev_r, next_r)
                transitions[key] = transitions.get(key, 0) + 1

        anomalies = []
        checked_pairs: set[tuple[str, str]] = set()

        for (src, dst), count in transitions.items():
            pair = tuple(sorted([src, dst]))
            if pair in checked_pairs:
                continue

            reverse_count = transitions.get((dst, src), 0)
            total = count + reverse_count

            if src != dst and total >= self.loop_threshold:
                checked_pairs.add(pair)

                severity = "medium"
                if total >= self.loop_threshold * 2:
                    severity = "high"
                if total >= self.loop_threshold * 3:
                    severity = "critical"

                anomalies.append({
                    "anomaly_type": "loop",
                    "severity": severity,
                    "description": f"页面 {src} 与 {dst} 之间存在循环跳转 ({total} 次)",
                    "page_url": f"{src} ↔ {dst}",
                    "metric_value": total,
                    "threshold": self.loop_threshold,
                    "suggestion": f"检查 {src} 和 {dst} 之间的导航逻辑，考虑简化流程或增加引导提示。",
                })

        return anomalies

    # ----------------------------------------------------------
    # 子检测器: 停留时间异常
    # ----------------------------------------------------------

    def _detect_long_dwell(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        检测用户在某页面停留时间过长的异常。
        
        算法: 检查事件中的 duration_ms 字段，
        若超过阈值则标记为异常。
        """
        anomalies = []

        for e in events:
            duration = e.get("duration_ms", e.get("durationMs"))
            if duration is None:
                continue

            duration = float(duration)
            if duration >= self.dwell_ms_threshold:
                route = e.get("route", e.get("page_url", "?"))
                elem = e.get("element_id", e.get("elementId", ""))

                severity = "low"
                if duration >= self.dwell_ms_threshold * 2:
                    severity = "medium"
                if duration >= self.dwell_ms_threshold * 4:
                    severity = "high"

                desc = f"用户在 {route} 页面停留 {duration:.0f}ms（阈值 {self.dwell_ms_threshold:.0f}ms）"
                if elem:
                    desc += f"，可能在元素 [{elem}] 处犹豫"

                anomalies.append({
                    "anomaly_type": "long_dwell",
                    "severity": severity,
                    "description": desc,
                    "page_url": route,
                    "metric_value": duration,
                    "threshold": self.dwell_ms_threshold,
                    "suggestion": f"优化 {route} 页面的信息层级和交互引导，降低用户决策成本。",
                })

        return anomalies

    # ----------------------------------------------------------
    # 子检测器: 路径熵
    # ----------------------------------------------------------

    def _detect_path_entropy(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        计算路径的 Shannon 熵，判断路径是否混乱。
        
        Shannon 熵公式:
            H = -Σ p(x) * log2(p(x))
        
        其中 p(x) 是每个转换的概率。
        """
        routes = []
        for e in events:
            route = e.get("route", e.get("page_url", ""))
            event_type = e.get("event_type", e.get("eventType", ""))
            if route and event_type not in ("pointer_move", "scroll"):
                routes.append(route)

        if len(routes) < 3:
            return []

        # 提取转换序列
        transitions = []
        for prev_r, next_r in zip(routes, routes[1:]):
            if prev_r != next_r:
                transitions.append(f"{prev_r}->{next_r}")

        if not transitions:
            return []

        # 计算 Shannon 熵
        counter = Counter(transitions)
        total = len(transitions)
        entropy = 0.0

        for count in counter.values():
            p = count / total
            if p > 0:
                entropy -= p * math.log2(p)

        anomalies = []
        if entropy >= self.entropy_threshold:
            severity = "medium"
            if entropy >= self.entropy_threshold * 1.5:
                severity = "high"

            anomalies.append({
                "anomaly_type": "high_path_entropy",
                "severity": severity,
                "description": (
                    f"用户路径熵值为 {entropy:.2f}（阈值 {self.entropy_threshold:.2f}），"
                    f"路径呈现高度随机性/混乱状态，用户可能在探索中迷失。"
                ),
                "page_url": None,
                "metric_value": round(entropy, 3),
                "threshold": self.entropy_threshold,
                "suggestion": "检查整体导航结构是否清晰，考虑增加面包屑导航或流程进度指示器。",
                "details": {
                    "unique_transitions": len(counter),
                    "total_transitions": total,
                    "top_transitions": counter.most_common(5),
                },
            })

        return anomalies

    # ----------------------------------------------------------
    # 子检测器: 愤怒点击
    # ----------------------------------------------------------

    def _detect_rage_clicks(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        检测用户在短时间内对同一元素反复点击（愤怒点击）。
        
        算法: 滑动时间窗口，统计同一元素在窗口内的点击次数。
        """
        click_events = []
        for e in events:
            event_type = e.get("event_type", e.get("eventType", ""))
            if event_type == "click":
                ts = self._parse_ts(e.get("timestamp", ""))
                elem = e.get("element_id", e.get("elementId", ""))
                if ts and elem:
                    click_events.append({"timestamp": ts, "element_id": elem, "event": e})

        if len(click_events) < self.rage_click_count:
            return []

        # 按元素分组
        by_element: dict[str, list] = defaultdict(list)
        for ce in click_events:
            by_element[ce["element_id"]].append(ce)

        anomalies = []
        for elem_id, clicks in by_element.items():
            if len(clicks) < self.rage_click_count:
                continue

            # 按时间排序
            clicks.sort(key=lambda c: c["timestamp"])

            # 滑动窗口检测
            for i in range(len(clicks) - self.rage_click_count + 1):
                window_start = clicks[i]["timestamp"]
                window_end = clicks[i + self.rage_click_count - 1]["timestamp"]
                delta_ms = (window_end - window_start).total_seconds() * 1000

                if delta_ms <= self.rage_click_window_ms:
                    route = clicks[i]["event"].get("route", "?")
                    anomalies.append({
                        "anomaly_type": "rage_click",
                        "severity": "high",
                        "description": (
                            f"用户在 {delta_ms:.0f}ms 内对元素 [{elem_id}] "
                            f"连续点击 {self.rage_click_count} 次（愤怒点击）"
                        ),
                        "page_url": route,
                        "metric_value": self.rage_click_count,
                        "threshold": float(self.rage_click_count),
                        "suggestion": f"检查元素 [{elem_id}] 是否有响应延迟或无反馈问题。",
                    })
                    break  # 每个元素只报告一次

        return anomalies

    # ----------------------------------------------------------
    # 子检测器: 死胡同
    # ----------------------------------------------------------

    def _detect_dead_ends(
        self,
        events: list[dict[str, Any]],
        path_graph: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """
        检测用户到达后无法继续前进的页面（"死胡同"）。
        
        算法: 在路径图中找到没有出边但被多次访问的节点。
        """
        edges = path_graph.get("edges", [])
        nodes = path_graph.get("nodes", [])

        if not edges or not nodes:
            return []

        # 收集有出边的节点
        has_outgoing = set()
        for edge in edges:
            has_outgoing.add(edge.get("source", ""))

        anomalies = []
        for node in nodes:
            node_id = node.get("id", "")
            visits = node.get("visit_count", 0)
            label = node.get("label", node.get("page_url", "?"))

            # 被访问 >= 2 次但没有出边
            if node_id not in has_outgoing and visits >= 2:
                anomalies.append({
                    "anomaly_type": "dead_end",
                    "severity": "medium",
                    "description": f"页面 [{label}] 被访问 {visits} 次但无出向转换（死胡同）",
                    "page_url": node.get("page_url", ""),
                    "metric_value": float(visits),
                    "threshold": 2.0,
                    "suggestion": f"检查 [{label}] 页面是否缺少明确的后续操作入口。",
                })

        return anomalies

    # ----------------------------------------------------------
    # 健康度评分
    # ----------------------------------------------------------

    @staticmethod
    def _calculate_health_score(
        anomalies: list[dict[str, Any]],
        event_count: int,
    ) -> float:
        """
        综合评估用户体验健康度 (0-100)。
        
        扣分规则:
        - critical 异常: -25 分
        - high 异常: -15 分
        - medium 异常: -10 分
        - low 异常: -5 分
        """
        score = 100.0
        deductions = {
            "critical": 25,
            "high": 15,
            "medium": 10,
            "low": 5,
        }

        for a in anomalies:
            severity = a.get("severity", "low")
            score -= deductions.get(severity, 5)

        return max(0.0, min(100.0, score))

    # ----------------------------------------------------------
    # 总结生成
    # ----------------------------------------------------------

    @staticmethod
    def _generate_summary(anomalies: list[dict[str, Any]]) -> str:
        """根据异常列表生成文字总结"""
        if not anomalies:
            return "未检测到显著异常路径，旅程整体流畅。"

        type_counts: dict[str, int] = {}
        for a in anomalies:
            t = a.get("anomaly_type", "unknown")
            type_counts[t] = type_counts.get(t, 0) + 1

        parts = []
        if "loop" in type_counts:
            parts.append(f"循环跳转 {type_counts['loop']} 处")
        if "long_dwell" in type_counts:
            parts.append(f"异常停留 {type_counts['long_dwell']} 处")
        if "high_path_entropy" in type_counts:
            parts.append("路径整体混乱（高熵）")
        if "rage_click" in type_counts:
            parts.append(f"愤怒点击 {type_counts['rage_click']} 处")
        if "dead_end" in type_counts:
            parts.append(f"死胡同页面 {type_counts['dead_end']} 个")

        summary = "检测到以下异常: " + "、".join(parts) + "。"

        # 最高严重度
        severities = [a.get("severity", "low") for a in anomalies]
        if "critical" in severities:
            summary += " ⚠️ 存在严重问题，建议立即排查。"
        elif "high" in severities:
            summary += " 建议重点关注高优先级异常。"

        return summary

    # ----------------------------------------------------------
    # 工具方法
    # ----------------------------------------------------------

    @staticmethod
    def _parse_ts(ts_value) -> Optional[datetime]:
        """解析时间戳"""
        if isinstance(ts_value, datetime):
            return ts_value
        if not ts_value:
            return None
        try:
            return datetime.fromisoformat(str(ts_value).replace("Z", "+00:00"))
        except ValueError:
            return None
