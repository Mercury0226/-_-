# -*- coding: utf-8 -*-
"""
AI 算法 API 路由 (ai_routes.py)
=================================
将算法模块的能力暴露为 FastAPI HTTP 接口，
供前端 Dashboard 和外部系统调用。

路由列表:
- POST /api/v1/ai/recognize-ui    — UI 元素识别
- POST /api/v1/ai/vectorize-path  — 操作序列矢量化
- POST /api/v1/ai/summarize       — 行为语义化分析
- POST /api/v1/ai/detect-anomaly  — 异常检测
- POST /api/v1/ai/full-analysis   — 一站式全量分析

"""

from __future__ import annotations

import time
import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from algorithm.ui_recognition import UIRecognizer
from algorithm.path_vectorizer import PathVectorizer
from algorithm.behavior_summarizer import BehaviorSummarizer
from algorithm.anomaly_detector import AnomalyDetector

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ai", tags=["AI Algorithm"])

# 单例实例
_recognizer = UIRecognizer()
_vectorizer = PathVectorizer()
_summarizer = BehaviorSummarizer()
_detector = AnomalyDetector()


# ============================================================
# 请求/响应模型
# ============================================================


class UIRecognitionRequest(BaseModel):
    """UI 识别请求"""
    image_base64: Optional[str] = Field(default=None, description="截图的 Base64 编码")
    image_url: Optional[str] = Field(default=None, description="截图的公开 URL")
    page_url: str = Field(default="", description="当前页面 URL")


class PathVectorizeRequest(BaseModel):
    """路径矢量化请求"""
    events: list[dict[str, Any]] = Field(..., min_length=1, description="行为事件列表")


class BehaviorSummarizeRequest(BaseModel):
    """行为语义化请求"""
    events: list[dict[str, Any]] = Field(..., min_length=1)
    path_graph: Optional[dict[str, Any]] = Field(default=None, description="路径图（可选）")
    scenario: Optional[str] = Field(default=None, description="场景: general/checkout/auth/browse")


class AnomalyDetectRequest(BaseModel):
    """异常检测请求"""
    events: list[dict[str, Any]] = Field(..., min_length=1)
    path_graph: Optional[dict[str, Any]] = Field(default=None)


class FullAnalysisRequest(BaseModel):
    """一站式全量分析请求"""
    events: list[dict[str, Any]] = Field(..., min_length=1)
    screenshots: Optional[dict[str, str]] = Field(
        default=None,
        description="按页面 URL 分组的截图 Base64 映射: {page_url: base64_string}",
    )
    include_ui_recognition: bool = Field(default=False, description="是否执行 UI 识别（需提供截图）")
    include_behavior_summary: bool = Field(default=True)
    include_anomaly_detection: bool = Field(default=True)


# ============================================================
# API 路由
# ============================================================


@router.post("/recognize-ui")
async def recognize_ui(req: UIRecognitionRequest) -> dict[str, Any]:
    """
    UI 元素识别接口

    接收页面截图（Base64 或 URL），返回识别到的 UI 元素列表。
    """
    start = time.time()

    if not req.image_base64 and not req.image_url:
        raise HTTPException(status_code=400, detail="请提供 image_base64 或 image_url")

    try:
        if req.image_base64:
            elements = await _recognizer.recognize_from_base64(
                req.image_base64, page_url=req.page_url,
            )
        else:
            elements = await _recognizer.recognize_from_url(
                req.image_url, page_url=req.page_url,  # type: ignore
            )

        elapsed_ms = (time.time() - start) * 1000
        return {
            "ok": True,
            "elements": elements,
            "count": len(elements),
            "processing_time_ms": round(elapsed_ms, 1),
        }
    except Exception as exc:
        logger.error("UI 识别失败: %s", exc)
        raise HTTPException(status_code=500, detail=f"UI 识别失败: {exc}") from exc


@router.post("/vectorize-path")
async def vectorize_path(req: PathVectorizeRequest) -> dict[str, Any]:
    """
    路径矢量化接口

    接收事件列表，返回矢量化路径图（节点 + 边），
    可直接供前端 D3.js 渲染。
    """
    start = time.time()

    try:
        graph = _vectorizer.vectorize(req.events)
        elapsed_ms = (time.time() - start) * 1000
        return {
            "ok": True,
            "path_graph": graph,
            "processing_time_ms": round(elapsed_ms, 1),
        }
    except Exception as exc:
        logger.error("路径矢量化失败: %s", exc)
        raise HTTPException(status_code=500, detail=f"路径矢量化失败: {exc}") from exc


@router.post("/summarize")
async def summarize_behavior(req: BehaviorSummarizeRequest) -> dict[str, Any]:
    """
    行为语义化接口

    接收事件列表和可选路径图，调用 LLM 生成自然语言行为摘要。
    """
    start = time.time()

    try:
        summary = await _summarizer.summarize(
            req.events,
            path_graph=req.path_graph,
            scenario=req.scenario,
        )
        elapsed_ms = (time.time() - start) * 1000
        return {
            "ok": True,
            "summary": summary,
            "processing_time_ms": round(elapsed_ms, 1),
        }
    except Exception as exc:
        logger.error("行为语义化失败: %s", exc)
        raise HTTPException(status_code=500, detail=f"行为语义化失败: {exc}") from exc


@router.post("/detect-anomaly")
async def detect_anomaly(req: AnomalyDetectRequest) -> dict[str, Any]:
    """
    异常检测接口

    对事件序列执行全面的异常检测（循环、停留、路径熵、愤怒点击）。
    """
    start = time.time()

    try:
        report = _detector.detect(req.events, path_graph=req.path_graph)
        elapsed_ms = (time.time() - start) * 1000
        return {
            "ok": True,
            "report": report,
            "processing_time_ms": round(elapsed_ms, 1),
        }
    except Exception as exc:
        logger.error("异常检测失败: %s", exc)
        raise HTTPException(status_code=500, detail=f"异常检测失败: {exc}") from exc


@router.post("/full-analysis")
async def full_analysis(req: FullAnalysisRequest) -> dict[str, Any]:
    """
    一站式全量分析接口

    依次执行: 路径矢量化 → UI 识别 → 异常检测 → 行为语义化，
    返回完整分析报告。
    """
    start = time.time()

    try:
        # Step 1: 路径矢量化（始终执行）
        path_graph = _vectorizer.vectorize(req.events)

        # Step 2: UI 识别（可选，需要截图）
        ui_elements_by_page: dict[str, list] = {}
        if req.include_ui_recognition and req.screenshots:
            for page_url, b64 in req.screenshots.items():
                try:
                    elements = await _recognizer.recognize_from_base64(b64, page_url=page_url)
                    ui_elements_by_page[page_url] = elements
                except Exception as e:
                    logger.warning("UI 识别跳过 %s: %s", page_url, e)

            # 重新矢量化，挂载 UI 元素
            if ui_elements_by_page:
                path_graph = _vectorizer.vectorize(req.events, ui_elements_by_page)

        # Step 3: 异常检测（可选）
        anomaly_report = None
        if req.include_anomaly_detection:
            anomaly_report = _detector.detect(req.events, path_graph=path_graph)

        # Step 4: 行为语义化（可选）
        behavior_summary = None
        if req.include_behavior_summary:
            try:
                behavior_summary = await _summarizer.summarize(
                    req.events, path_graph=path_graph,
                )
            except Exception as e:
                logger.warning("行为语义化跳过: %s", e)
                behavior_summary = {"error": str(e)}

        elapsed_ms = (time.time() - start) * 1000

        return {
            "ok": True,
            "path_graph": path_graph,
            "ui_elements": ui_elements_by_page if ui_elements_by_page else None,
            "anomaly_report": anomaly_report,
            "behavior_summary": behavior_summary,
            "processing_time_ms": round(elapsed_ms, 1),
        }

    except Exception as exc:
        logger.error("全量分析失败: %s", exc)
        raise HTTPException(status_code=500, detail=f"全量分析失败: {exc}") from exc
