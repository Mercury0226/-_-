# -*- coding: utf-8 -*-
"""
UI 元素识别模块 (ui_recognition.py)
====================================
通过 GPT-4o-mini Vision API 对 UI 截图进行元素识别，
将截图中的按钮、输入框、导航栏等 UI 组件提取为结构化数据。

技术原理:
---------
1. **输入**: 前端 SDK 采集的页面截图 (Base64 / URL)
2. **处理**: 调用 Vision 模型，结合精心设计的 Prompt 模板，
   让模型以 JSON 格式输出每个 UI 元素的类型、标签、边界框坐标
3. **输出**: 结构化的 UIElement 列表，可直接用于路径矢量化

设计方法:
---------
- 采用「Vision-Language Model (VLM)」方案而非传统 YOLO/DETR 目标检测
- 优势: 零样本泛化能力强，无需额外训练集，能同时输出语义标签
- 参考: ScreenAI (2024), GPT-4V UI Analysis 等前沿工作

"""

from __future__ import annotations

import base64
import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ============================================================
# 常量与配置
# ============================================================

# UI 元素类型映射（Vision 模型可能返回多种表述）
UI_TYPE_ALIASES: dict[str, str] = {
    "button": "button",
    "btn": "button",
    "link": "link",
    "anchor": "link",
    "a": "link",
    "input": "input_field",
    "text_field": "input_field",
    "textbox": "input_field",
    "textarea": "input_field",
    "search": "input_field",
    "image": "image",
    "img": "image",
    "icon": "icon",
    "text": "text",
    "label": "text",
    "heading": "text",
    "paragraph": "text",
    "navbar": "navbar",
    "navigation": "navbar",
    "nav": "navbar",
    "tab": "tab",
    "card": "card",
    "modal": "modal",
    "dialog": "modal",
    "popup": "modal",
    "dropdown": "dropdown",
    "select": "dropdown",
    "checkbox": "checkbox",
    "toggle": "toggle",
    "switch": "toggle",
    "slider": "slider",
    "range": "slider",
}

# 默认置信度阈值
DEFAULT_CONFIDENCE_THRESHOLD = 0.6

# Vision Prompt 模板 —— 用于指导 GPT-4o 识别 UI 元素
UI_RECOGNITION_PROMPT = """你是一个专业的 UI 视觉分析助手。请分析以下截图中所有可见的 UI 元素。

## 任务要求
1. 识别截图中的所有交互性 UI 元素（按钮、输入框、链接、导航栏、图标等）
2. 对每个元素给出：类型、文字标签、位置坐标（边界框）、置信度
3. 边界框坐标为相对于图片左上角的像素值 (x, y, width, height)

## 输出格式
请以严格 JSON 数组返回，每个元素格式如下：
```json
[
  {
    "element_type": "button",
    "label": "立即支付",
    "bounding_box": {"x": 120, "y": 680, "width": 200, "height": 48},
    "confidence": 0.95
  }
]
```

## 元素类型枚举
button, input_field, link, image, icon, text, navbar, tab, card, modal, dropdown, checkbox, toggle, slider

## 注意事项
- 只返回 JSON 数组，不要返回其他文字说明
- 如果无法确定元素类型，使用 "other"
- confidence 取值范围 0.0 ~ 1.0
- 忽略纯装饰性元素（如背景图案）"""


# ============================================================
# UIRecognizer 类
# ============================================================


class UIRecognizer:
    """
    基于 Vision 模型 (GPT-4o-mini) 的 UI 元素识别器。

    使用方式:
    ---------
    >>> recognizer = UIRecognizer(api_key="sk-xxx")
    >>> elements = await recognizer.recognize_from_base64(screenshot_b64)
    >>> print(elements)
    [{"element_type": "button", "label": "提交", ...}, ...]
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-4o-mini",
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
        max_image_size: int = 2048,
    ) -> None:
        self.api_key = api_key or os.getenv("VISION_MODEL_API_KEY") or os.getenv("OPENAI_API_KEY", "")
        self.model = model
        self.confidence_threshold = confidence_threshold
        self.max_image_size = max_image_size
        self._client = None  # 延迟初始化

    # ----------------------------------------------------------
    # OpenAI 客户端（延迟创建，避免 import 时就要求 key）
    # ----------------------------------------------------------

    def _get_client(self):
        """延迟初始化 OpenAI 客户端"""
        if self._client is None:
            try:
                from openai import AsyncOpenAI
                self._client = AsyncOpenAI(api_key=self.api_key)
            except ImportError:
                raise RuntimeError(
                    "依赖 openai 包，请运行: pip install openai>=1.14.0"
                )
        return self._client

    # ----------------------------------------------------------
    # 核心方法: 从截图识别 UI 元素
    # ----------------------------------------------------------

    async def recognize_from_base64(
        self,
        image_base64: str,
        page_url: str = "",
        custom_prompt: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """
        从 Base64 编码的截图中识别 UI 元素。

        Parameters
        ----------
        image_base64 : str
            截图的 Base64 编码字符串 (不含 data:image/ 前缀)
        page_url : str
            当前页面 URL，用于附加到识别结果中
        custom_prompt : str, optional
            自定义 Prompt，覆盖默认模板

        Returns
        -------
        list[dict]
            识别到的 UI 元素列表，每个元素包含:
            element_type, label, bounding_box, confidence, page_url
        """
        client = self._get_client()
        prompt = custom_prompt or UI_RECOGNITION_PROMPT

        # 构建 Vision API 请求
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_base64}",
                            "detail": "high",
                        },
                    },
                ],
            }
        ]

        try:
            response = await client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=4096,
                temperature=0.1,  # 低温度保证结果稳定
            )

            raw_text = response.choices[0].message.content or "[]"
            elements = self._parse_response(raw_text)

            # 附加 page_url 并过滤低置信度结果
            result = []
            for elem in elements:
                elem["page_url"] = page_url
                elem["element_type"] = self._normalize_type(elem.get("element_type", "other"))
                if elem.get("confidence", 0) >= self.confidence_threshold:
                    result.append(elem)

            logger.info(
                "UI 识别完成: 共 %d 个元素 (过滤前 %d 个), page=%s",
                len(result), len(elements), page_url,
            )
            return result

        except Exception as exc:
            logger.error("Vision API 调用失败: %s", exc)
            raise

    async def recognize_from_url(
        self,
        image_url: str,
        page_url: str = "",
        custom_prompt: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """
        从图片 URL 识别 UI 元素（适用于已上传至 CDN 的截图）。

        Parameters
        ----------
        image_url : str
            截图的公开可访问 URL
        page_url : str
            当前页面 URL
        custom_prompt : str, optional
            自定义 Prompt

        Returns
        -------
        list[dict]
            识别到的 UI 元素列表
        """
        client = self._get_client()
        prompt = custom_prompt or UI_RECOGNITION_PROMPT

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": image_url, "detail": "high"},
                    },
                ],
            }
        ]

        try:
            response = await client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=4096,
                temperature=0.1,
            )

            raw_text = response.choices[0].message.content or "[]"
            elements = self._parse_response(raw_text)

            result = []
            for elem in elements:
                elem["page_url"] = page_url
                elem["element_type"] = self._normalize_type(elem.get("element_type", "other"))
                if elem.get("confidence", 0) >= self.confidence_threshold:
                    result.append(elem)

            logger.info(
                "UI 识别完成 (URL 模式): 共 %d 个元素, page=%s",
                len(result), page_url,
            )
            return result

        except Exception as exc:
            logger.error("Vision API 调用失败 (URL 模式): %s", exc)
            raise

    async def recognize_from_file(
        self,
        file_path: str,
        page_url: str = "",
    ) -> list[dict[str, Any]]:
        """从本地文件路径读取截图并识别 UI 元素（便于测试）"""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"截图文件不存在: {file_path}")

        image_bytes = path.read_bytes()
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
        return await self.recognize_from_base64(image_b64, page_url=page_url)

    # ----------------------------------------------------------
    # 内部工具方法
    # ----------------------------------------------------------

    @staticmethod
    def _parse_response(raw_text: str) -> list[dict[str, Any]]:
        """
        解析 Vision 模型返回的文本，提取 JSON 数组。
        模型可能在 JSON 前后附加说明文字，需要容错处理。
        """
        text = raw_text.strip()

        # 尝试直接解析
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return parsed
            if isinstance(parsed, dict) and "elements" in parsed:
                return parsed["elements"]
            return [parsed]
        except json.JSONDecodeError:
            pass

        # 尝试提取 ```json ... ``` 代码块
        if "```" in text:
            start = text.find("```json")
            if start == -1:
                start = text.find("```")
            if start != -1:
                start = text.index("\n", start) + 1
                end = text.find("```", start)
                if end != -1:
                    json_str = text[start:end].strip()
                    try:
                        parsed = json.loads(json_str)
                        return parsed if isinstance(parsed, list) else [parsed]
                    except json.JSONDecodeError:
                        pass

        # 尝试找到第一个 [ 和最后一个 ]
        first_bracket = text.find("[")
        last_bracket = text.rfind("]")
        if first_bracket != -1 and last_bracket != -1 and last_bracket > first_bracket:
            json_str = text[first_bracket:last_bracket + 1]
            try:
                parsed = json.loads(json_str)
                return parsed if isinstance(parsed, list) else [parsed]
            except json.JSONDecodeError:
                pass

        logger.warning("无法解析 Vision 模型返回: %s", text[:200])
        return []

    @staticmethod
    def _normalize_type(raw_type: str) -> str:
        """将模型返回的元素类型标准化"""
        normalized = raw_type.lower().strip().replace(" ", "_").replace("-", "_")
        return UI_TYPE_ALIASES.get(normalized, normalized)

    @staticmethod
    def image_file_to_base64(file_path: str) -> str:
        """工具方法：将本地图片文件转为 Base64 字符串"""
        return base64.b64encode(Path(file_path).read_bytes()).decode("utf-8")
