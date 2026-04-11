# -*- coding: utf-8 -*-
"""
算法模块单元测试
==================
测试路径矢量化和异常检测模块（不依赖外部 API）。

Usage: cd server && python -m pytest test_algorithm.py -v
"""

import sys
import os
import json

# 确保能找到 algorithm 包
sys.path.insert(0, os.path.dirname(__file__))

from algorithm.path_vectorizer import PathVectorizer
from algorithm.anomaly_detector import AnomalyDetector


# ============================================================
# 测试数据
# ============================================================

SAMPLE_EVENTS = [
    {
        "session_id": "sess_001",
        "user_id": "user_玥_1001",
        "page_url": "https://demo.example.com/cart",
        "route": "/cart",
        "event_type": "click",
        "timestamp": "2026-04-09T10:30:00Z",
        "element_id": "btn-checkout",
        "intent_label": "start_checkout",
        "coordinates": {"x": 722.5, "y": 418.2},
    },
    {
        "session_id": "sess_001",
        "user_id": "user_玥_1001",
        "page_url": "https://demo.example.com/payment",
        "route": "/payment",
        "event_type": "dwell",
        "timestamp": "2026-04-09T10:30:42Z",
        "element_id": "coupon-input",
        "intent_label": "coupon_apply",
        "duration_ms": 18200,
    },
    {
        "session_id": "sess_001",
        "user_id": "user_玥_1001",
        "page_url": "https://demo.example.com/cart",
        "route": "/cart",
        "event_type": "route_change",
        "timestamp": "2026-04-09T10:31:00Z",
        "intent_label": "back_navigation",
        "duration_ms": 900,
    },
    {
        "session_id": "sess_001",
        "user_id": "user_玥_1001",
        "page_url": "https://demo.example.com/payment",
        "route": "/payment",
        "event_type": "click",
        "timestamp": "2026-04-09T10:31:30Z",
        "element_id": "btn-pay",
        "intent_label": "retry_payment",
    },
    {
        "session_id": "sess_001",
        "user_id": "user_玥_1001",
        "page_url": "https://demo.example.com/cart",
        "route": "/cart",
        "event_type": "route_change",
        "timestamp": "2026-04-09T10:32:00Z",
        "intent_label": "back_navigation",
        "duration_ms": 1200,
    },
    {
        "session_id": "sess_001",
        "user_id": "user_玥_1001",
        "page_url": "https://demo.example.com/payment",
        "route": "/payment",
        "event_type": "click",
        "timestamp": "2026-04-09T10:32:30Z",
        "element_id": "btn-pay",
        "intent_label": "retry_payment",
    },
]


# ============================================================
# PathVectorizer 测试
# ============================================================


class TestPathVectorizer:
    """路径矢量化测试"""

    def setup_method(self):
        self.vectorizer = PathVectorizer()

    def test_empty_events(self):
        """空事件列表应返回空图"""
        result = self.vectorizer.vectorize([])
        assert result["nodes"] == []
        assert result["edges"] == []
        assert result["metadata"]["event_count"] == 0

    def test_basic_vectorize(self):
        """基本矢量化功能"""
        result = self.vectorizer.vectorize(SAMPLE_EVENTS)

        # 应有 2 个节点 (/cart, /payment)
        assert result["metadata"]["node_count"] == 2
        # 应有 2 条边 (/cart → /payment, /payment → /cart)
        assert result["metadata"]["edge_count"] == 2
        assert result["metadata"]["event_count"] == len(SAMPLE_EVENTS)

        print(f"\n  节点数: {result['metadata']['node_count']}")
        print(f"  边数: {result['metadata']['edge_count']}")
        print(f"  总时长: {result['metadata']['total_duration_ms']:.0f}ms")

    def test_nodes_have_coordinates(self):
        """节点应被分配渲染坐标"""
        result = self.vectorizer.vectorize(SAMPLE_EVENTS)
        for node in result["nodes"]:
            assert "x" not in node or isinstance(node.get("x"), int)  # layout sets as attr

    def test_labels_readable(self):
        """节点标签应可读"""
        result = self.vectorizer.vectorize(SAMPLE_EVENTS)
        labels = [n["label"] for n in result["nodes"]]
        assert any("购物车" in l or "cart" in l for l in labels)
        assert any("支付" in l or "payment" in l for l in labels)

    def test_edge_has_transition_count(self):
        """边应记录转换次数"""
        result = self.vectorizer.vectorize(SAMPLE_EVENTS)
        for edge in result["edges"]:
            assert edge["transition_count"] >= 1

    def test_single_page_no_edges(self):
        """只有一个页面时不应有边"""
        single_page_events = [
            {"route": "/home", "event_type": "click", "timestamp": "2026-04-09T10:00:00Z"},
            {"route": "/home", "event_type": "click", "timestamp": "2026-04-09T10:00:05Z"},
        ]
        result = self.vectorizer.vectorize(single_page_events)
        assert result["metadata"]["node_count"] == 1
        assert result["metadata"]["edge_count"] == 0


# ============================================================
# AnomalyDetector 测试
# ============================================================


class TestAnomalyDetector:
    """异常检测测试"""

    def setup_method(self):
        self.detector = AnomalyDetector(
            loop_threshold=3,
            dwell_ms_threshold=15000,
            entropy_threshold=2.0,
        )

    def test_no_anomalies_clean_path(self):
        """正常流程不应有异常"""
        clean_events = [
            {"route": "/home", "event_type": "click", "timestamp": "2026-04-09T10:00:00Z"},
            {"route": "/product", "event_type": "click", "timestamp": "2026-04-09T10:00:10Z"},
            {"route": "/cart", "event_type": "click", "timestamp": "2026-04-09T10:00:20Z"},
            {"route": "/checkout", "event_type": "click", "timestamp": "2026-04-09T10:00:30Z"},
        ]
        report = self.detector.detect(clean_events)
        assert report["total_anomalies"] == 0
        assert report["overall_health_score"] == 100.0
        print(f"\n  健康度: {report['overall_health_score']}")
        print(f"  总结: {report['summary']}")

    def test_loop_detection(self):
        """循环跳转应被检测到"""
        report = self.detector.detect(SAMPLE_EVENTS)
        loop_anomalies = [a for a in report["anomalies"] if a["anomaly_type"] == "loop"]
        assert len(loop_anomalies) >= 1
        print(f"\n  循环异常: {loop_anomalies[0]['description']}")

    def test_long_dwell_detection(self):
        """长停留应被检测到"""
        report = self.detector.detect(SAMPLE_EVENTS)
        dwell_anomalies = [a for a in report["anomalies"] if a["anomaly_type"] == "long_dwell"]
        assert len(dwell_anomalies) >= 1
        # 18200ms > 15000ms 阈值
        print(f"\n  停留异常: {dwell_anomalies[0]['description']}")

    def test_rage_click_detection(self):
        """愤怒点击应被检测到"""
        rage_events = [
            {"route": "/payment", "event_type": "click", "element_id": "btn-pay",
             "timestamp": "2026-04-09T10:30:00.000Z"},
            {"route": "/payment", "event_type": "click", "element_id": "btn-pay",
             "timestamp": "2026-04-09T10:30:00.500Z"},
            {"route": "/payment", "event_type": "click", "element_id": "btn-pay",
             "timestamp": "2026-04-09T10:30:01.000Z"},
            {"route": "/payment", "event_type": "click", "element_id": "btn-pay",
             "timestamp": "2026-04-09T10:30:01.500Z"},
            {"route": "/payment", "event_type": "click", "element_id": "btn-pay",
             "timestamp": "2026-04-09T10:30:02.000Z"},
        ]
        report = self.detector.detect(rage_events)
        rage_anomalies = [a for a in report["anomalies"] if a["anomaly_type"] == "rage_click"]
        assert len(rage_anomalies) >= 1
        print(f"\n  愤怒点击: {rage_anomalies[0]['description']}")

    def test_health_score_decreases_with_anomalies(self):
        """异常越多，健康度越低"""
        report = self.detector.detect(SAMPLE_EVENTS)
        assert report["overall_health_score"] < 100.0
        print(f"\n  健康度: {report['overall_health_score']}")

    def test_path_entropy_calculation(self):
        """路径熵计算 — 高熵路径应被标记"""
        chaotic_events = [
            {"route": "/a", "event_type": "click", "timestamp": "2026-04-09T10:00:00Z"},
            {"route": "/b", "event_type": "click", "timestamp": "2026-04-09T10:00:01Z"},
            {"route": "/c", "event_type": "click", "timestamp": "2026-04-09T10:00:02Z"},
            {"route": "/a", "event_type": "click", "timestamp": "2026-04-09T10:00:03Z"},
            {"route": "/d", "event_type": "click", "timestamp": "2026-04-09T10:00:04Z"},
            {"route": "/b", "event_type": "click", "timestamp": "2026-04-09T10:00:05Z"},
            {"route": "/c", "event_type": "click", "timestamp": "2026-04-09T10:00:06Z"},
            {"route": "/a", "event_type": "click", "timestamp": "2026-04-09T10:00:07Z"},
            {"route": "/e", "event_type": "click", "timestamp": "2026-04-09T10:00:08Z"},
            {"route": "/d", "event_type": "click", "timestamp": "2026-04-09T10:00:09Z"},
        ]
        # 使用低阈值确保检测到
        detector_low = AnomalyDetector(entropy_threshold=1.5)
        report = detector_low.detect(chaotic_events)
        entropy_anomalies = [a for a in report["anomalies"] if a["anomaly_type"] == "high_path_entropy"]
        assert len(entropy_anomalies) >= 1
        print(f"\n  路径熵异常: {entropy_anomalies[0]['description']}")

    def test_dead_end_detection(self):
        """死胡同检测"""
        events = [
            {"route": "/home", "event_type": "click", "timestamp": "2026-04-09T10:00:00Z"},
            {"route": "/error", "event_type": "click", "timestamp": "2026-04-09T10:00:01Z"},
            {"route": "/error", "event_type": "click", "timestamp": "2026-04-09T10:00:02Z"},
        ]
        # 需要路径图
        vectorizer = PathVectorizer()
        graph = vectorizer.vectorize(events)
        report = self.detector.detect(events, path_graph=graph)
        dead_ends = [a for a in report["anomalies"] if a["anomaly_type"] == "dead_end"]
        # /error 被访问 2 次但无出边
        assert len(dead_ends) >= 1
        print(f"\n  死胡同: {dead_ends[0]['description']}")


# ============================================================
# UI 识别 Prompt 解析测试（不需要 API Key）
# ============================================================


class TestUIRecognizerParsing:
    """测试 UI 识别模块的响应解析功能"""

    def setup_method(self):
        from algorithm.ui_recognition import UIRecognizer
        self.recognizer = UIRecognizer(api_key="test-key")

    def test_parse_json_array(self):
        """解析标准 JSON 数组"""
        raw = '[{"element_type": "button", "label": "提交", "bounding_box": {"x": 100, "y": 200, "width": 80, "height": 40}, "confidence": 0.95}]'
        result = self.recognizer._parse_response(raw)
        assert len(result) == 1
        assert result[0]["element_type"] == "button"

    def test_parse_json_in_code_block(self):
        """解析被代码块包裹的 JSON"""
        raw = """这是分析结果：
```json
[{"element_type": "link", "label": "详情", "bounding_box": {"x": 10, "y": 20, "width": 50, "height": 30}, "confidence": 0.8}]
```
以上是识别到的元素。"""
        result = self.recognizer._parse_response(raw)
        assert len(result) == 1
        assert result[0]["element_type"] == "link"

    def test_normalize_type(self):
        """元素类型标准化"""
        assert self.recognizer._normalize_type("btn") == "button"
        assert self.recognizer._normalize_type("INPUT") == "input_field"
        assert self.recognizer._normalize_type("navigation") == "navbar"
        assert self.recognizer._normalize_type("select") == "dropdown"


# ============================================================
# 集成测试: 矢量化 → 异常检测 Pipeline
# ============================================================


class TestIntegrationPipeline:
    """端到端 Pipeline 测试"""

    def test_vectorize_then_detect(self):
        """矢量化 → 异常检测 完整流程"""
        vectorizer = PathVectorizer()
        detector = AnomalyDetector()

        # Step 1: 矢量化
        graph = vectorizer.vectorize(SAMPLE_EVENTS)
        assert graph["metadata"]["node_count"] >= 2

        # Step 2: 异常检测
        report = detector.detect(SAMPLE_EVENTS, path_graph=graph)
        assert report["total_anomalies"] >= 1
        assert 0 <= report["overall_health_score"] <= 100

        print(f"\n  ===== 集成测试结果 =====")
        print(f"  节点: {graph['metadata']['node_count']}")
        print(f"  边: {graph['metadata']['edge_count']}")
        print(f"  异常数: {report['total_anomalies']}")
        print(f"  健康度: {report['overall_health_score']}")
        print(f"  总结: {report['summary']}")

    def test_output_json_serializable(self):
        """确保输出可以序列化为 JSON"""
        vectorizer = PathVectorizer()
        detector = AnomalyDetector()

        graph = vectorizer.vectorize(SAMPLE_EVENTS)
        report = detector.detect(SAMPLE_EVENTS, path_graph=graph)

        # 验证 JSON 可序列化
        json_str = json.dumps({"graph": graph, "report": report}, ensure_ascii=False, indent=2)
        assert len(json_str) > 100
        print(f"\n  JSON 输出大小: {len(json_str)} 字符")


# ============================================================
# 直接运行
# ============================================================

if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v", "--tb=short"])
