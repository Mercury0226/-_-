"""
算法模块 —— 用户旅程图自动化与异常分析平台

本模块包含三大核心子系统:
1. ui_recognition  — 基于 Vision 模型的 UI 元素识别
2. behavior_summarizer — 基于 LLM 的行为语义转换
3. anomaly_detector — 路径熵 / 停留时间 异常检测
4. path_vectorizer — 操作序列 → 矢量路径图转换
"""

from .ui_recognition import UIRecognizer
from .behavior_summarizer import BehaviorSummarizer
from .anomaly_detector import AnomalyDetector
from .path_vectorizer import PathVectorizer

__all__ = [
    "UIRecognizer",
    "BehaviorSummarizer",
    "AnomalyDetector",
    "PathVectorizer",
]
