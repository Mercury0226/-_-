# -*- coding: utf-8 -*-
"""
Sprint 2 单元测试
==================
测试综合报告生成 (US-06/07) 和人工反馈存储 (US-08) 模块。

Usage: cd server && python -m pytest test_sprint2.py -v
"""

import sys
import os
import json

sys.path.insert(0, os.path.dirname(__file__))

from algorithm.path_vectorizer import PathVectorizer
from algorithm.anomaly_detector import AnomalyDetector
from algorithm.report_generator import ReportGenerator
from algorithm.feedback_store import FeedbackStore


# ============================================================
# 测试数据
# ============================================================

SAMPLE_EVENTS = [
    {
        "session_id": "sess_002",
        "user_id": "user_测试_2001",
        "page_url": "https://demo.example.com/home",
        "route": "/home",
        "event_type": "click",
        "timestamp": "2026-04-16T14:00:00Z",
        "element_id": "nav-products",
        "intent_label": "browse_products",
    },
    {
        "session_id": "sess_002",
        "user_id": "user_测试_2001",
        "page_url": "https://demo.example.com/product",
        "route": "/product",
        "event_type": "click",
        "timestamp": "2026-04-16T14:00:15Z",
        "element_id": "btn-add-cart",
        "intent_label": "add_to_cart",
    },
    {
        "session_id": "sess_002",
        "user_id": "user_测试_2001",
        "page_url": "https://demo.example.com/product",
        "route": "/product",
        "event_type": "dwell",
        "timestamp": "2026-04-16T14:00:30Z",
        "element_id": "product-gallery",
        "intent_label": "view_images",
        "duration_ms": 22000,
    },
    {
        "session_id": "sess_002",
        "user_id": "user_测试_2001",
        "page_url": "https://demo.example.com/cart",
        "route": "/cart",
        "event_type": "click",
        "timestamp": "2026-04-16T14:01:00Z",
        "element_id": "btn-checkout",
        "intent_label": "start_checkout",
    },
    {
        "session_id": "sess_002",
        "user_id": "user_测试_2001",
        "page_url": "https://demo.example.com/checkout",
        "route": "/checkout",
        "event_type": "dwell",
        "timestamp": "2026-04-16T14:01:30Z",
        "element_id": "form-address",
        "intent_label": "fill_address",
        "duration_ms": 35000,
    },
    {
        "session_id": "sess_002",
        "user_id": "user_测试_2001",
        "page_url": "https://demo.example.com/cart",
        "route": "/cart",
        "event_type": "route_change",
        "timestamp": "2026-04-16T14:02:10Z",
        "intent_label": "back_navigation",
    },
    {
        "session_id": "sess_002",
        "user_id": "user_测试_2001",
        "page_url": "https://demo.example.com/checkout",
        "route": "/checkout",
        "event_type": "click",
        "timestamp": "2026-04-16T14:02:40Z",
        "element_id": "btn-pay",
        "intent_label": "submit_payment",
    },
    {
        "session_id": "sess_002",
        "user_id": "user_测试_2001",
        "page_url": "https://demo.example.com/cart",
        "route": "/cart",
        "event_type": "route_change",
        "timestamp": "2026-04-16T14:03:00Z",
        "intent_label": "back_navigation",
    },
    {
        "session_id": "sess_002",
        "user_id": "user_测试_2001",
        "page_url": "https://demo.example.com/checkout",
        "route": "/checkout",
        "event_type": "click",
        "timestamp": "2026-04-16T14:03:30Z",
        "element_id": "btn-pay",
        "intent_label": "submit_payment",
    },
    {
        "session_id": "sess_002",
        "user_id": "user_测试_2001",
        "page_url": "https://demo.example.com/success",
        "route": "/success",
        "event_type": "click",
        "timestamp": "2026-04-16T14:04:00Z",
        "element_id": "btn-done",
        "intent_label": "order_complete",
    },
]


# ============================================================
# ReportGenerator 测试
# ============================================================


class TestReportGenerator:
    """综合报告生成测试"""

    def setup_method(self):
        self.generator = ReportGenerator()
        self.vectorizer = PathVectorizer()
        self.detector = AnomalyDetector()

    def test_generate_basic_report(self):
        """基本报告生成"""
        graph = self.vectorizer.vectorize(SAMPLE_EVENTS)
        anomaly_report = self.detector.detect(SAMPLE_EVENTS, path_graph=graph)
        report = self.generator.generate(
            SAMPLE_EVENTS, path_graph=graph, anomaly_report=anomaly_report,
        )

        assert "global_metrics" in report
        assert "node_heatmap" in report
        assert "ranked_anomalies" in report
        assert "improvement_suggestions" in report
        assert "report_metadata" in report

        print(f"\n  报告生成成功:")
        print(f"  - 全局指标: {len(report['global_metrics'])} 项")
        print(f"  - 节点热力: {len(report['node_heatmap'])} 个")
        print(f"  - 异常排序: {len(report['ranked_anomalies'])} 条")
        print(f"  - 改进建议: {len(report['improvement_suggestions'])} 条")

    def test_anomaly_ranking_us06(self):
        """US-06: 异常应按严重程度和频次排序"""
        graph = self.vectorizer.vectorize(SAMPLE_EVENTS)
        anomaly_report = self.detector.detect(SAMPLE_EVENTS, path_graph=graph)
        report = self.generator.generate(
            SAMPLE_EVENTS, path_graph=graph, anomaly_report=anomaly_report,
        )

        ranked = report["ranked_anomalies"]
        if len(ranked) >= 2:
            # 确认按 priority_score 降序
            for i in range(len(ranked) - 1):
                assert ranked[i]["priority_score"] >= ranked[i + 1]["priority_score"]
            # 确认有排名
            assert ranked[0]["rank"] == 1

        print(f"\n  异常排序 (US-06):")
        for a in ranked[:3]:
            print(f"    #{a['rank']} [{a['severity']}] {a['description'][:50]}... (score={a['priority_score']})")

    def test_node_heatmap_us07(self):
        """US-07: 节点应有点击热度和停留时长"""
        graph = self.vectorizer.vectorize(SAMPLE_EVENTS)
        report = self.generator.generate(SAMPLE_EVENTS, path_graph=graph)

        heatmap = report["node_heatmap"]
        assert len(heatmap) >= 1

        for node in heatmap:
            assert "click_count" in node
            assert "click_heat" in node
            assert "total_dwell_ms" in node
            assert "avg_dwell_ms" in node
            assert "heat_level" in node
            assert node["click_heat"] >= 0.0
            assert node["click_heat"] <= 1.0
            assert node["heat_level"] in ("hot", "warm", "cool", "cold")

        print(f"\n  节点热力 (US-07):")
        for node in heatmap:
            print(f"    {node['label']}: clicks={node['click_count']}, "
                  f"heat={node['click_heat']:.2f} [{node['heat_level']}], "
                  f"dwell={node['avg_dwell_ms']:.0f}ms")

    def test_global_metrics(self):
        """全局指标应包含关键字段"""
        graph = self.vectorizer.vectorize(SAMPLE_EVENTS)
        anomaly_report = self.detector.detect(SAMPLE_EVENTS, path_graph=graph)
        report = self.generator.generate(
            SAMPLE_EVENTS, path_graph=graph, anomaly_report=anomaly_report,
        )

        metrics = report["global_metrics"]
        assert metrics["total_events"] == len(SAMPLE_EVENTS)
        assert metrics["unique_pages"] >= 4  # home, product, cart, checkout, success
        assert "event_type_distribution" in metrics
        assert "health_score" in metrics

    def test_empty_events(self):
        """空事件列表应返回有效报告"""
        report = self.generator.generate([])
        assert report["global_metrics"]["total_events"] == 0
        assert report["node_heatmap"] == []
        assert report["ranked_anomalies"] == []

    def test_report_json_serializable(self):
        """报告应可序列化为 JSON"""
        graph = self.vectorizer.vectorize(SAMPLE_EVENTS)
        anomaly_report = self.detector.detect(SAMPLE_EVENTS, path_graph=graph)
        report = self.generator.generate(
            SAMPLE_EVENTS, path_graph=graph, anomaly_report=anomaly_report,
        )
        json_str = json.dumps(report, ensure_ascii=False, indent=2)
        assert len(json_str) > 100
        print(f"\n  报告 JSON 大小: {len(json_str)} 字符")


# ============================================================
# FeedbackStore 测试
# ============================================================


class TestFeedbackStore:
    """人工反馈存储测试 (US-08)"""

    def setup_method(self):
        self.store = FeedbackStore()

    def test_add_feedback(self):
        """添加反馈"""
        result = self.store.add_feedback(
            page_url="/checkout",
            element_type_predicted="button",
            element_type_corrected="button",
            label_predicted="提交",
            label_corrected="确认支付",
            confidence=0.82,
            is_correct=False,
        )
        assert result["accepted"] is True
        assert "feedback_id" in result
        assert result["total_feedback_count"] == 1
        print(f"\n  反馈已记录: {result['feedback_id']}")

    def test_multiple_feedback(self):
        """多条反馈统计"""
        feedbacks = [
            {"page_url": "/home", "type_pred": "button", "type_corr": "button",
             "conf": 0.95, "correct": True},
            {"page_url": "/home", "type_pred": "link", "type_corr": "link",
             "conf": 0.88, "correct": True},
            {"page_url": "/checkout", "type_pred": "button", "type_corr": "input_field",
             "conf": 0.62, "correct": False},
            {"page_url": "/checkout", "type_pred": "icon", "type_corr": "button",
             "conf": 0.55, "correct": False},
            {"page_url": "/home", "type_pred": "navbar", "type_corr": "navbar",
             "conf": 0.91, "correct": True},
        ]

        for fb in feedbacks:
            self.store.add_feedback(
                page_url=fb["page_url"],
                element_type_predicted=fb["type_pred"],
                element_type_corrected=fb["type_corr"],
                label_predicted="",
                label_corrected="",
                confidence=fb["conf"],
                is_correct=fb["correct"],
            )

        # 查询统计
        stats = self.store.get_accuracy_stats()
        assert stats["total_count"] == 5
        assert stats["correct_count"] == 3
        assert stats["overall_accuracy"] == 0.6

        print(f"\n  准确率统计 (US-08):")
        print(f"    总体准确率: {stats['overall_accuracy']}")
        print(f"    总数: {stats['total_count']}, 正确: {stats['correct_count']}")
        print(f"    按类型: {stats['accuracy_by_type']}")
        print(f"    置信度分布: {stats['confidence_distribution']}")

    def test_query_by_page(self):
        """按页面查询反馈"""
        self.store.add_feedback("/home", "button", "button", "OK", "OK", 0.9, True)
        self.store.add_feedback("/cart", "link", "button", "详情", "加购", 0.7, False)
        self.store.add_feedback("/home", "icon", "icon", "x", "关闭", 0.85, True)

        home_feedbacks = self.store.get_feedback_by_page("/home")
        assert len(home_feedbacks) == 2

        cart_feedbacks = self.store.get_feedback_by_page("/cart")
        assert len(cart_feedbacks) == 1

    def test_accuracy_by_type(self):
        """按元素类型统计准确率"""
        self.store.add_feedback("/p", "button", "button", "", "", 0.9, True)
        self.store.add_feedback("/p", "button", "link", "", "", 0.6, False)
        self.store.add_feedback("/p", "icon", "icon", "", "", 0.85, True)

        stats = self.store.get_accuracy_stats()
        assert stats["accuracy_by_type"]["button"]["accuracy"] == 0.5
        assert stats["accuracy_by_type"]["icon"]["accuracy"] == 1.0

    def test_confidence_distribution(self):
        """置信度分布统计"""
        self.store.add_feedback("/p", "a", "a", "", "", 0.95, True)
        self.store.add_feedback("/p", "b", "b", "", "", 0.72, True)
        self.store.add_feedback("/p", "c", "d", "", "", 0.55, False)

        stats = self.store.get_accuracy_stats()
        dist = stats["confidence_distribution"]
        assert dist["min"] == 0.55
        assert dist["max"] == 0.95
        assert dist["below_0.8"] == 2
        assert dist["above_0.9"] == 1

    def test_empty_store_stats(self):
        """空存储应返回合理默认值"""
        stats = self.store.get_accuracy_stats()
        assert stats["total_count"] == 0
        assert stats["overall_accuracy"] is None


# ============================================================
# Sprint 2 集成测试
# ============================================================


class TestSprint2Integration:
    """Sprint 2 端到端集成测试"""

    def test_full_sprint2_pipeline(self):
        """路径矢量化 → 异常检测 → 报告生成 完整流程"""
        vectorizer = PathVectorizer()
        detector = AnomalyDetector()
        generator = ReportGenerator()

        # Step 1: 路径矢量化
        graph = vectorizer.vectorize(SAMPLE_EVENTS)
        assert graph["metadata"]["node_count"] >= 4

        # Step 2: 异常检测
        anomaly_report = detector.detect(SAMPLE_EVENTS, path_graph=graph)

        # Step 3: 综合报告
        report = generator.generate(
            SAMPLE_EVENTS,
            path_graph=graph,
            anomaly_report=anomaly_report,
        )

        assert report["global_metrics"]["total_events"] == len(SAMPLE_EVENTS)
        assert len(report["node_heatmap"]) >= 4
        assert "report_metadata" in report

        print(f"\n  ===== Sprint 2 集成测试结果 =====")
        print(f"  节点: {graph['metadata']['node_count']}")
        print(f"  边: {graph['metadata']['edge_count']}")
        print(f"  异常数: {anomaly_report['total_anomalies']}")
        print(f"  健康度: {anomaly_report['overall_health_score']}")
        print(f"  热力节点: {len(report['node_heatmap'])}")
        print(f"  排序异常: {len(report['ranked_anomalies'])}")
        print(f"  改进建议: {len(report['improvement_suggestions'])}")

    def test_feedback_and_stats_pipeline(self):
        """反馈提交 → 统计查询 完整流程"""
        store = FeedbackStore()

        # 模拟真实使用场景
        store.add_feedback("/home", "button", "button", "登录", "登录", 0.92, True)
        store.add_feedback("/home", "input_field", "input_field", "搜索框", "搜索框", 0.88, True)
        store.add_feedback("/product", "button", "link", "详情", "跳转链接", 0.65, False)
        store.add_feedback("/checkout", "dropdown", "dropdown", "选择", "省份选择", 0.78, True)
        store.add_feedback("/checkout", "button", "button", "提交", "确认支付", 0.85, True, "标签需修正")

        stats = store.get_accuracy_stats()

        assert stats["total_count"] == 5
        assert stats["correct_count"] == 4
        assert stats["overall_accuracy"] == 0.8

        print(f"\n  ===== 反馈统计集成测试 =====")
        print(f"  总体准确率: {stats['overall_accuracy']}")
        print(f"  按类型准确率: {json.dumps(stats['accuracy_by_type'], ensure_ascii=False)}")
        print(f"  按页面准确率: {json.dumps(stats['accuracy_by_page'], ensure_ascii=False)}")


# ============================================================
# 直接运行
# ============================================================

if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v", "--tb=short"])
