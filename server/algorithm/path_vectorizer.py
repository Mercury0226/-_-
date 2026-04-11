# -*- coding: utf-8 -*-
"""
路径矢量化模块 (path_vectorizer.py)
=====================================
将用户的操作事件序列转化为有向图（矢量化路径图），
图中节点代表页面 / UI 状态，边代表页面间的转换关系。

技术原理:
---------
1. **页面聚合**: 将连续的操作事件按 page_url / route 聚合为"节点"
2. **转换提取**: 相邻不同页面之间产生"边"，记录转换次数与触发元素
3. **停留计算**: 根据时间戳差值计算每个页面的平均停留时间
4. **UI 元素挂载**: 将 UI 识别结果附加到对应的节点上

输出可直接供 D3.js / AntV G6 前端组件渲染。

"""

from __future__ import annotations

import hashlib
import logging
from collections import defaultdict
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ============================================================
# 数据结构
# ============================================================


class PathNode:
    """路径图节点 — 代表一个页面或 UI 状态"""

    def __init__(self, node_id: str, page_url: str, label: str) -> None:
        self.node_id = node_id
        self.page_url = page_url
        self.label = label
        self.visit_count: int = 0
        self.total_dwell_ms: float = 0.0
        self.ui_elements: list[dict[str, Any]] = []

    @property
    def avg_dwell_ms(self) -> float:
        """平均停留时间 (毫秒)"""
        return self.total_dwell_ms / max(self.visit_count, 1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.node_id,
            "page_url": self.page_url,
            "label": self.label,
            "visit_count": self.visit_count,
            "avg_dwell_ms": round(self.avg_dwell_ms, 1),
            "ui_elements": self.ui_elements,
        }


class PathEdge:
    """路径图边 — 代表页面之间的一次转换"""

    def __init__(self, source_id: str, target_id: str) -> None:
        self.source_id = source_id
        self.target_id = target_id
        self.transition_count: int = 0
        self.total_transition_ms: float = 0.0
        self.action_types: list[str] = []
        self.trigger_elements: list[str] = []

    @property
    def avg_transition_ms(self) -> float:
        return self.total_transition_ms / max(self.transition_count, 1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source_id,
            "target": self.target_id,
            "transition_count": self.transition_count,
            "avg_transition_ms": round(self.avg_transition_ms, 1),
            "action_types": list(set(self.action_types)),
            "trigger_elements": list(set(self.trigger_elements)),
        }


# ============================================================
# PathVectorizer 类
# ============================================================


class PathVectorizer:
    """
    将原始操作事件序列转换为矢量化路径图 (有向图)。

    使用方式:
    ---------
    >>> vectorizer = PathVectorizer()
    >>> graph = vectorizer.vectorize(events)
    >>> print(graph["nodes"])  # 节点列表
    >>> print(graph["edges"])  # 边列表
    """

    def __init__(self, max_path_length: int = 500) -> None:
        self.max_path_length = max_path_length

    # ----------------------------------------------------------
    # 核心方法
    # ----------------------------------------------------------

    def vectorize(
        self,
        events: list[dict[str, Any]],
        ui_elements_by_page: Optional[dict[str, list[dict]]] = None,
    ) -> dict[str, Any]:
        """
        将事件序列转换为路径图。

        Parameters
        ----------
        events : list[dict]
            行为事件列表，每个事件至少包含:
            - route (str): 当前页面路由
            - event_type (str): 事件类型
            - timestamp (str/datetime): 时间戳
            可选字段:
            - element_id (str): 操作的元素
            - intent_label (str): 意图标签
            - duration_ms (int): 在该页面停留的时间
        ui_elements_by_page : dict, optional
            按页面 URL 分组的 UI 元素识别结果

        Returns
        -------
        dict
            路径图数据，包含 nodes, edges, metadata
        """
        if not events:
            return {"nodes": [], "edges": [], "metadata": {"event_count": 0}}

        # 截断过长序列
        events = events[:self.max_path_length]

        # 按时间排序
        sorted_events = sorted(events, key=lambda e: self._parse_ts(e.get("timestamp", "")))

        # 构建节点和边
        nodes: dict[str, PathNode] = {}
        edges: dict[str, PathEdge] = {}

        prev_route: Optional[str] = None
        prev_ts: Optional[datetime] = None

        for event in sorted_events:
            route = event.get("route", event.get("page_url", "/unknown"))
            event_type = event.get("event_type", event.get("eventType", "unknown"))

            # 跳过指针移动事件 (不参与路径图构建)
            if event_type in ("pointer_move", "scroll"):
                continue

            ts = self._parse_ts(event.get("timestamp", ""))
            node_id = self._route_to_node_id(route)

            # 创建或更新节点
            if node_id not in nodes:
                label = self._route_to_label(route)
                nodes[node_id] = PathNode(node_id, route, label)
            node = nodes[node_id]
            node.visit_count += 1

            # 记录停留时间
            duration_ms = event.get("duration_ms", event.get("durationMs"))
            if duration_ms is not None:
                node.total_dwell_ms += float(duration_ms)
            elif prev_ts and ts and prev_route == route:
                delta = (ts - prev_ts).total_seconds() * 1000
                if 0 < delta < 300_000:  # 最多 5 分钟
                    node.total_dwell_ms += delta

            # 创建转换边
            if prev_route and prev_route != route:
                prev_node_id = self._route_to_node_id(prev_route)
                edge_key = f"{prev_node_id}->{node_id}"

                if edge_key not in edges:
                    edges[edge_key] = PathEdge(prev_node_id, node_id)

                edge = edges[edge_key]
                edge.transition_count += 1
                edge.action_types.append(event_type)

                # 记录转换时间
                if prev_ts and ts:
                    delta = (ts - prev_ts).total_seconds() * 1000
                    if delta > 0:
                        edge.total_transition_ms += delta

                # 记录触发元素
                elem_id = event.get("element_id", event.get("elementId"))
                if elem_id:
                    edge.trigger_elements.append(elem_id)

            prev_route = route
            prev_ts = ts

        # 挂载 UI 元素识别结果
        if ui_elements_by_page:
            for node_id, node in nodes.items():
                page_elements = ui_elements_by_page.get(node.page_url, [])
                node.ui_elements = page_elements

        # 为前端分配布局坐标
        node_list = list(nodes.values())
        self._assign_layout(node_list)

        # 汇总
        total_duration = 0.0
        if sorted_events:
            first_ts = self._parse_ts(sorted_events[0].get("timestamp", ""))
            last_ts = self._parse_ts(sorted_events[-1].get("timestamp", ""))
            if first_ts and last_ts:
                total_duration = (last_ts - first_ts).total_seconds() * 1000

        result = {
            "nodes": [n.to_dict() for n in node_list],
            "edges": [e.to_dict() for e in edges.values()],
            "metadata": {
                "event_count": len(events),
                "node_count": len(node_list),
                "edge_count": len(edges),
                "total_duration_ms": round(total_duration, 1),
            },
        }

        logger.info(
            "路径矢量化完成: %d 节点, %d 边, %.1fs 总时长",
            len(node_list), len(edges), total_duration / 1000,
        )
        return result

    # ----------------------------------------------------------
    # 布局算法: 简单的水平排列
    # ----------------------------------------------------------

    @staticmethod
    def _assign_layout(
        nodes: list[PathNode],
        canvas_width: int = 860,
        canvas_height: int = 420,
        margin: int = 80,
    ) -> None:
        """
        为节点分配前端渲染坐标。
        采用按访问顺序从左到右水平排列的简单策略。
        """
        n = len(nodes)
        if n == 0:
            return

        usable_width = canvas_width - 2 * margin
        usable_height = canvas_height - 2 * margin

        if n == 1:
            nodes[0].x = canvas_width // 2  # type: ignore
            nodes[0].y = canvas_height // 2  # type: ignore
            return

        spacing_x = usable_width / max(n - 1, 1)

        for i, node in enumerate(nodes):
            node.x = margin + int(i * spacing_x)  # type: ignore
            # 交错上下排列，避免重叠
            if i % 2 == 0:
                node.y = margin + usable_height // 3  # type: ignore
            else:
                node.y = margin + 2 * usable_height // 3  # type: ignore

    # ----------------------------------------------------------
    # 工具方法
    # ----------------------------------------------------------

    @staticmethod
    def _route_to_node_id(route: str) -> str:
        """将路由路径转为稳定的短 ID"""
        h = hashlib.md5(route.encode()).hexdigest()[:6]
        return f"n_{h}"

    @staticmethod
    def _route_to_label(route: str) -> str:
        """将路由路径转为可读标签"""
        route = route.strip("/")
        if not route:
            return "首页"

        # 常见路由的中文映射
        label_map = {
            "cart": "购物车",
            "checkout": "结算页",
            "payment": "支付页",
            "login": "登录页",
            "register": "注册页",
            "signup": "注册页",
            "home": "首页",
            "index": "首页",
            "profile": "个人中心",
            "settings": "设置",
            "search": "搜索",
            "product": "商品详情",
            "order": "订单",
            "orders": "订单列表",
            "confirm": "确认页",
            "success": "成功页",
            "error": "错误页",
            "404": "404页",
        }

        # 取最后一段路径
        last_segment = route.split("/")[-1].lower()
        return label_map.get(last_segment, f"/{route}")

    @staticmethod
    def _parse_ts(ts_value) -> Optional[datetime]:
        """解析多种格式的时间戳"""
        if isinstance(ts_value, datetime):
            return ts_value
        if not ts_value:
            return None

        ts_str = str(ts_value)
        formats = [
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S.%f%z",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(ts_str.replace("+00:00", "Z").rstrip("Z") + "Z", fmt)
            except ValueError:
                continue

        # 兜底: 尝试 fromisoformat
        try:
            return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except ValueError:
            logger.warning("无法解析时间戳: %s", ts_str)
            return None
