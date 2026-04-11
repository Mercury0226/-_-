# -*- coding: utf-8 -*-
"""
Prompt 模板库 (templates.py)
==============================
集中管理所有 Prompt 模板，供 UI 识别和行为分析模块调用。
按场景分类，支持参数化填充。

"""

# ============================================================
# UI 识别 Prompt
# ============================================================

UI_RECOGNITION_SYSTEM = (
    "你是一个专业的 UI 视觉分析助手，能精确识别截图中的 UI 组件。"
    "你的输出必须是规范的 JSON 格式。"
)

UI_RECOGNITION_DETAILED = """请分析以下 UI 截图，识别所有可交互的 UI 元素。

## 识别规则
1. 标注所有按钮 (button)、输入框 (input_field)、链接 (link)、
   导航栏 (navbar)、选项卡 (tab)、下拉菜单 (dropdown)、
   复选框 (checkbox)、开关 (toggle)、图标 (icon)
2. 对于文字型元素，仅标注标题、关键提示文字
3. 忽略纯装饰性元素
4. 每个元素需要给出:
   - element_type: 元素类型
   - label: 元素上的文字 (若无文字则描述功能，如"返回箭头")
   - bounding_box: {x, y, width, height} 像素坐标
   - confidence: 0.0 ~ 1.0 置信度

## 输出
严格 JSON 数组:
```json
[
  {"element_type": "button", "label": "提交", "bounding_box": {"x": 100, "y": 200, "width": 80, "height": 40}, "confidence": 0.95}
]
```"""

UI_RECOGNITION_MOBILE = """请分析以下移动端 UI 截图，识别所有 UI 元素。

## 移动端特殊注意
- 底部导航栏 (tabs) 需要逐个识别
- 浮动按钮 (FAB) 需单独标注
- 手势区域（如下拉刷新）可忽略
- 注意状态栏高度偏移

## 输出
严格 JSON 数组:
```json
[
  {"element_type": "tab", "label": "首页", "bounding_box": {"x": 0, "y": 750, "width": 90, "height": 50}, "confidence": 0.9}
]
```"""


# ============================================================
# 行为语义化 Prompt (详见 behavior_summarizer.py)
# ============================================================

BEHAVIOR_SYSTEM = (
    "你是一位资深的用户体验数据分析师。"
    "你的分析需要数据驱动且包含可操作建议。"
    "请始终用中文输出，格式为严格 JSON。"
)

# 通用场景
BEHAVIOR_GENERAL = """分析以下用户行为日志:

## 数据
{event_data}

## 路径摘要
{path_summary}

## 输出 JSON
{{
  "user_intent": "用户主要意图",
  "behavior_narrative": "2-3 句描述",
  "pain_points": ["痛点1", "痛点2"],
  "intent_labels": ["标签1", "标签2"],
  "efficiency_rating": "efficient|moderate|inefficient",
  "recommendations": ["建议1", "建议2"]
}}"""

# 电商结算
BEHAVIOR_CHECKOUT = """分析以下用户在电商结算流程中的行为:

## 数据
{event_data}

## 路径摘要
{path_summary}

## 重点关注
- 支付犹豫信号
- 优惠券使用摩擦
- 不必要的回退

## 输出 JSON
{{
  "user_intent": "...",
  "behavior_narrative": "...",
  "pain_points": [".."],
  "intent_labels": [".."],
  "efficiency_rating": "efficient|moderate|inefficient",
  "recommendations": [".."],
  "checkout_insights": {{
    "hesitation_detected": true/false,
    "coupon_friction": true/false,
    "unnecessary_backtracking": true/false,
    "estimated_conversion_risk": "low|medium|high"
  }}
}}"""

# 注册登录
BEHAVIOR_AUTH = """分析以下用户的注册/登录行为:

## 数据
{event_data}

## 路径摘要
{path_summary}

## 重点关注
- 表单填写摩擦
- 放弃注册信号
- 验证流程阻塞

## 输出 JSON
{{
  "user_intent": "...",
  "behavior_narrative": "...",
  "pain_points": [".."],
  "intent_labels": [".."],
  "efficiency_rating": "efficient|moderate|inefficient",
  "recommendations": [".."]
}}"""

# 浏览探索
BEHAVIOR_BROWSE = """分析以下用户的浏览探索行为:

## 数据
{event_data}

## 路径摘要
{path_summary}

## 重点关注
- 浏览目的性
- 内容发现效率
- 迷失信号

## 输出 JSON
{{
  "user_intent": "...",
  "behavior_narrative": "...",
  "pain_points": [".."],
  "intent_labels": [".."],
  "efficiency_rating": "efficient|moderate|inefficient",
  "recommendations": [".."]
}}"""


# ============================================================
# 模板注册表
# ============================================================

PROMPT_REGISTRY = {
    "ui_recognition": {
        "system": UI_RECOGNITION_SYSTEM,
        "default": UI_RECOGNITION_DETAILED,
        "mobile": UI_RECOGNITION_MOBILE,
    },
    "behavior": {
        "system": BEHAVIOR_SYSTEM,
        "general": BEHAVIOR_GENERAL,
        "checkout": BEHAVIOR_CHECKOUT,
        "auth": BEHAVIOR_AUTH,
        "browse": BEHAVIOR_BROWSE,
    },
}


def get_prompt(category: str, variant: str = "default") -> str:
    """获取指定类别和变体的 Prompt 模板"""
    cat = PROMPT_REGISTRY.get(category, {})
    if variant not in cat:
        variant = list(cat.keys())[0] if cat else "default"
    return cat.get(variant, "")
