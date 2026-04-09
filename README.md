# AI-driven User Journey Map (UJM) Analyzer

面向 PM 与研发的底层脚手架：通过前端 SDK 采集行为日志，后端进行异常识别与 AI 语义分析，再由可视化看板展示用户旅程路径与痛点。

## 项目目录结构

```text
.
├─ sdk/
│  └─ tracker.js
├─ server/
│  ├─ main.py
│  └─ requirements.txt
├─ dashboard/
│  ├─ UJMCanvas.jsx
│  ├─ index.html
│  ├─ package.json
│  ├─ postcss.config.js
│  ├─ tailwind.config.js
│  ├─ vite.config.js
│  └─ src/
│     ├─ App.jsx
│     ├─ index.css
│     └─ main.jsx
├─ schemas/
│  └─ behavior-log.example.json
├─ .env.example
└─ README.md
```

## 核心能力说明

1. `sdk/tracker.js`
- 单例采集器，静默监听点击、输入、滚动、路由变化与停留时长。
- 内置脱敏：自动屏蔽密码字段与疑似银行卡号。
- 异步上报：优先使用 Beacon API，回退到 `fetch(keepalive)`。

2. `server/main.py`
- FastAPI 日志接收接口：`POST /api/v1/logs/ingest`。
- Pydantic 校验：统一字段模型，事件序列强约束。
- 异常检测：Loop 路径熵异常 + 停留时长阈值异常。
- UTF-8 全链路：接口响应与示例数据支持中文生僻字（如“玥”）。

3. `dashboard/UJMCanvas.jsx`
- 使用 D3 渲染用户旅程矢量路径。
- 异常节点红色高亮。
- 点击节点后在右侧面板展示 AI 语义分析占位信息。

## 快速启动（本地）

## 一键可运行验收（推荐 PM 使用）

在项目根目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\one_click_acceptance.ps1
```

脚本会自动完成：

1. 检查 Python 与 Node 环境。
2. 创建后端虚拟环境并安装依赖。
3. 启动 FastAPI，执行健康检查。
4. 发送标准行为日志样例并校验分析返回。
5. 安装并构建 Dashboard。
6. 输出“验收通过/失败”结果并自动停止后端进程。

如果执行成功，即代表当前仓库具备“可运行、可联调、可验收”的基线能力。

### 1) 准备环境变量

复制根目录 `.env.example`，按需填入真实配置。

### 2) 启动后端 FastAPI

```bash
cd server
python -m venv .venv
# Windows:
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

健康检查：`GET http://localhost:8000/health`

### 3) 启动 Dashboard

```bash
cd dashboard
npm install
npm run dev
```

打开：`http://localhost:5173`

### 4) 在业务前端接入 SDK

```javascript
import { initUJMTracker } from './sdk/tracker.js';

initUJMTracker({
  endpoint: 'http://localhost:8000/api/v1/logs/ingest',
  appId: 'checkout-web',
  flushInterval: 5000,
  maxBuffer: 20,
});
```

## API 协议示例

标准行为日志示例见：`schemas/behavior-log.example.json`。

## 实时联动效果（监测某台电脑指针）

### 1) 启动后端与看板

```bash
# terminal A
cd server
.venv\Scripts\activate
uvicorn main:app --host 0.0.0.0 --port 8000

# terminal B
cd dashboard
npm run dev
```

看板地址：`http://localhost:5173`

### 2) 在被监测电脑接入 SDK

```javascript
import { initUJMTracker } from './sdk/tracker.js';

const tracker = initUJMTracker({
  endpoint: 'http://127.0.0.1:8000/api/v1/logs/ingest',
  appId: 'checkout-web',
  userId: 'user_demo',
  capturePointer: true,
  pointerSampleMs: 120,
});

console.log('deviceId=', tracker.getDeviceId());
```

### 3) 在看板输入这台电脑的 deviceId

看板顶部“实时设备监控”区域输入 deviceId 后，会建立 WebSocket：

- `ws://127.0.0.1:8000/ws/live-pointer/{deviceId}`

成功后你会看到：

1. WebSocket 状态变为 `connected`
2. 旅程图上出现 LIVE 指针标记并实时移动
3. “最近坐标”持续更新

### 4) 调试接口

- 获取当前有实时数据的设备：`GET /api/v1/live-pointer/devices`
- 获取某设备最近一次坐标：`GET /api/v1/live-pointer/{deviceId}/latest`

## 后续扩展建议

1. 在 `server/main.py` 中接入 MongoDB/Redis 实存与缓存。
2. 增加 AI 路由：CV（UI-to-Vector）与 LLM（语义总结）真实调用。
3. 为 SDK 增加采样率、重试队列、离线缓存与版本化协议。
4. 在 dashboard 增加时间轴回放和异常过滤器。
