# -*- coding: utf-8 -*-
"""
人工反馈存储模块 (feedback_store.py)
======================================
Sprint 2 新增模块 —— 算法工程师 王顺凯

对应用户故事:
    US-08: 作为算法工程师，我希望系统能够显示识别置信度
    并支持少量人工校正反馈，从而持续优化 UI 识别与 Prompt 效果。

功能:
-----
1. 接收并存储用户对 UI 识别结果的校正反馈
2. 按页面 URL 查询历史反馈
3. 计算识别准确率指标（基于反馈数据）
4. 为后续模型微调或 Prompt 优化提供数据基础

技术原理:
---------
- 使用内存字典存储反馈记录（课程项目级别，后续可替换为持久化存储）
- 准确率计算: accuracy = correct_count / total_count
- 支持按元素类型、页面维度统计置信度分布

"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Optional

_UTC = timezone.utc

logger = logging.getLogger(__name__)


class FeedbackRecord:
    """单条反馈记录"""

    def __init__(
        self,
        page_url: str,
        element_type_predicted: str,
        element_type_corrected: str,
        label_predicted: str,
        label_corrected: str,
        confidence: float,
        is_correct: bool,
        user_comment: str = "",
    ) -> None:
        self.feedback_id = str(uuid.uuid4())[:8]
        self.page_url = page_url
        self.element_type_predicted = element_type_predicted
        self.element_type_corrected = element_type_corrected
        self.label_predicted = label_predicted
        self.label_corrected = label_corrected
        self.confidence = confidence
        self.is_correct = is_correct
        self.user_comment = user_comment
        self.created_at = datetime.now(tz=_UTC).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "feedback_id": self.feedback_id,
            "page_url": self.page_url,
            "element_type_predicted": self.element_type_predicted,
            "element_type_corrected": self.element_type_corrected,
            "label_predicted": self.label_predicted,
            "label_corrected": self.label_corrected,
            "confidence": self.confidence,
            "is_correct": self.is_correct,
            "user_comment": self.user_comment,
            "created_at": self.created_at,
        }


class FeedbackStore:
    """
    人工反馈存储与统计服务。

    使用方式:
    ---------
    >>> store = FeedbackStore()
    >>> store.add_feedback(
    ...     page_url="/checkout",
    ...     element_type_predicted="button",
    ...     element_type_corrected="button",
    ...     label_predicted="提交订单",
    ...     label_corrected="确认支付",
    ...     confidence=0.82,
    ...     is_correct=False,
    ... )
    >>> stats = store.get_accuracy_stats()
    >>> print(stats["overall_accuracy"])
    """

    def __init__(self) -> None:
        self._records: list[FeedbackRecord] = []
        self._by_page: dict[str, list[FeedbackRecord]] = defaultdict(list)

    # ----------------------------------------------------------
    # 写入
    # ----------------------------------------------------------

    def add_feedback(
        self,
        page_url: str,
        element_type_predicted: str,
        element_type_corrected: str,
        label_predicted: str,
        label_corrected: str,
        confidence: float,
        is_correct: bool,
        user_comment: str = "",
    ) -> dict[str, Any]:
        """
        添加一条反馈记录。

        Returns
        -------
        dict
            包含 feedback_id 和确认信息
        """
        record = FeedbackRecord(
            page_url=page_url,
            element_type_predicted=element_type_predicted,
            element_type_corrected=element_type_corrected,
            label_predicted=label_predicted,
            label_corrected=label_corrected,
            confidence=confidence,
            is_correct=is_correct,
            user_comment=user_comment,
        )

        self._records.append(record)
        self._by_page[page_url].append(record)

        logger.info(
            "反馈已记录 [%s]: %s → %s (correct=%s, conf=%.2f)",
            record.feedback_id, element_type_predicted,
            element_type_corrected, is_correct, confidence,
        )

        return {
            "feedback_id": record.feedback_id,
            "accepted": True,
            "total_feedback_count": len(self._records),
        }

    # ----------------------------------------------------------
    # 查询
    # ----------------------------------------------------------

    def get_feedback_by_page(self, page_url: str) -> list[dict[str, Any]]:
        """查询某页面的所有反馈记录"""
        records = self._by_page.get(page_url, [])
        return [r.to_dict() for r in records]

    def get_all_feedback(self, limit: int = 100) -> list[dict[str, Any]]:
        """获取所有反馈记录"""
        return [r.to_dict() for r in self._records[-limit:]]

    # ----------------------------------------------------------
    # 统计
    # ----------------------------------------------------------

    def get_accuracy_stats(self) -> dict[str, Any]:
        """
        计算识别准确率统计。

        Returns
        -------
        dict
            - overall_accuracy: 总体准确率 (0-1)
            - total_count: 反馈总数
            - correct_count: 正确识别数
            - accuracy_by_type: 按元素类型的准确率
            - accuracy_by_page: 按页面的准确率
            - confidence_distribution: 置信度分布统计
        """
        if not self._records:
            return {
                "overall_accuracy": None,
                "total_count": 0,
                "correct_count": 0,
                "accuracy_by_type": {},
                "accuracy_by_page": {},
                "confidence_distribution": {},
            }

        total = len(self._records)
        correct = sum(1 for r in self._records if r.is_correct)
        overall_acc = correct / total

        # 按元素类型统计
        by_type: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "correct": 0})
        for r in self._records:
            key = r.element_type_predicted
            by_type[key]["total"] += 1
            if r.is_correct:
                by_type[key]["correct"] += 1

        accuracy_by_type = {
            k: {
                "accuracy": round(v["correct"] / max(v["total"], 1), 3),
                "total": v["total"],
                "correct": v["correct"],
            }
            for k, v in by_type.items()
        }

        # 按页面统计
        accuracy_by_page = {}
        for page_url, records in self._by_page.items():
            page_total = len(records)
            page_correct = sum(1 for r in records if r.is_correct)
            accuracy_by_page[page_url] = {
                "accuracy": round(page_correct / max(page_total, 1), 3),
                "total": page_total,
                "correct": page_correct,
            }

        # 置信度分布
        confidences = [r.confidence for r in self._records]
        conf_distribution = {
            "mean": round(sum(confidences) / len(confidences), 3),
            "min": round(min(confidences), 3),
            "max": round(max(confidences), 3),
            "below_0.8": sum(1 for c in confidences if c < 0.8),
            "above_0.9": sum(1 for c in confidences if c >= 0.9),
        }

        return {
            "overall_accuracy": round(overall_acc, 3),
            "total_count": total,
            "correct_count": correct,
            "accuracy_by_type": accuracy_by_type,
            "accuracy_by_page": accuracy_by_page,
            "confidence_distribution": conf_distribution,
        }

    def clear(self) -> None:
        """清空所有反馈记录"""
        self._records.clear()
        self._by_page.clear()
