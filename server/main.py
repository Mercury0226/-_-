# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field


class Coordinate(BaseModel):
    x: float = Field(..., description="X axis coordinate")
    y: float = Field(..., description="Y axis coordinate")


class BehaviorEvent(BaseModel):
    model_config = ConfigDict(extra="allow", str_strip_whitespace=True, populate_by_name=True)

    session_id: str = Field(..., min_length=3, alias="sessionId")
    user_id: str = Field(..., min_length=1, description="Supports UTF-8 chars like 玥", alias="userId")
    device_id: str | None = Field(default=None, alias="deviceId")
    page_url: str = Field(..., alias="pageUrl")
    route: str
    event_type: Literal["click", "scroll", "input", "route_change", "dwell", "unload", "pointer_move"] = Field(
        ..., alias="eventType"
    )
    timestamp: datetime
    element_id: str | None = Field(default=None, alias="elementId")
    intent_label: str = Field(..., min_length=1, alias="intentLabel")
    coordinates: Coordinate | None = None
    duration_ms: int | None = Field(default=None, ge=0, alias="durationMs")
    metadata: dict[str, Any] = Field(default_factory=dict)


class IngestPayload(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    schema_version: str = Field(default="1.0.0", alias="schemaVersion")
    encoding: Literal["utf-8", "UTF-8"] = Field(default="utf-8")
    sent_at: datetime = Field(..., alias="sentAt")
    events: list[BehaviorEvent] = Field(..., min_length=1)


class AnomalyResult(BaseModel):
    loop_entropy_anomaly: bool
    time_threshold_anomaly: bool
    summary: str


app = FastAPI(
    title="AI-driven UJM Analyzer API",
    version="0.3.0",
    description="AI-driven UJM Analyzer: CV, LLM, report generation & feedback (Sprint 2)",
    default_response_class=JSONResponse,
)

# ---- 挂载 AI 算法路由 (王顺凯) ----
try:
    from algorithm.ai_routes import router as ai_router
    app.include_router(ai_router)
except ImportError:
    import warnings
    warnings.warn("algorithm 模块未安装，AI 路由已跳过")


class LivePointerHub:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = {}
        self._latest: dict[str, dict[str, Any]] = {}

    async def connect(self, device_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.setdefault(device_id, set()).add(websocket)

    def disconnect(self, device_id: str, websocket: WebSocket) -> None:
        sockets = self._connections.get(device_id)
        if not sockets:
            return
        sockets.discard(websocket)
        if not sockets:
            self._connections.pop(device_id, None)

    async def broadcast(self, device_id: str, payload: dict[str, Any]) -> None:
        self._latest[device_id] = payload
        sockets = self._connections.get(device_id, set()).copy()
        stale_sockets: list[WebSocket] = []

        for socket in sockets:
            try:
                await socket.send_json(payload)
            except Exception:  # noqa: BLE001
                stale_sockets.append(socket)

        for socket in stale_sockets:
            self.disconnect(device_id, socket)

    def latest_by_device(self, device_id: str) -> dict[str, Any] | None:
        return self._latest.get(device_id)

    def devices(self) -> list[str]:
        return sorted(self._latest.keys())


pointer_hub = LivePointerHub()


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "encoding": "utf-8",
        "service": "ujm-analyzer",
        "message": "支持中文与生僻字：玥",
    }


@app.get("/api/v1/live-pointer/devices")
def list_live_pointer_devices() -> dict[str, Any]:
    return {"devices": pointer_hub.devices(), "encoding": "utf-8"}


@app.get("/api/v1/live-pointer/{device_id}/latest")
def get_latest_pointer(device_id: str) -> dict[str, Any]:
    latest = pointer_hub.latest_by_device(device_id)
    if not latest:
        raise HTTPException(status_code=404, detail="pointer_not_found")
    return {"deviceId": device_id, "latest": latest, "encoding": "utf-8"}


@app.websocket("/ws/live-pointer/{device_id}")
async def live_pointer_ws(websocket: WebSocket, device_id: str) -> None:
    await pointer_hub.connect(device_id, websocket)
    try:
        latest = pointer_hub.latest_by_device(device_id)
        if latest:
            await websocket.send_json(latest)
        while True:
            # Keep the socket alive and allow future bidirectional control messages.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pointer_hub.disconnect(device_id, websocket)
    except Exception:  # noqa: BLE001
        pointer_hub.disconnect(device_id, websocket)


def detect_loop_anomaly(events: list[BehaviorEvent], loop_threshold: int = 3) -> bool:
    routes = [event.route for event in events if event.route]
    if len(routes) < loop_threshold + 1:
        return False

    transitions: dict[tuple[str, str], int] = {}
    for prev_route, next_route in zip(routes, routes[1:]):
        key = (prev_route, next_route)
        transitions[key] = transitions.get(key, 0) + 1

    # Simple path entropy proxy: repeated back-and-forth transitions.
    for (src, dst), count in transitions.items():
        reverse_count = transitions.get((dst, src), 0)
        if src != dst and count + reverse_count >= loop_threshold:
            return True
    return False


def detect_time_anomaly(events: list[BehaviorEvent], dwell_ms_threshold: int = 15000) -> bool:
    dwell_events = [event for event in events if event.duration_ms is not None]
    if not dwell_events:
        return False
    return any((event.duration_ms or 0) >= dwell_ms_threshold for event in dwell_events)


def summarize_behavior(events: list[BehaviorEvent], loop_flag: bool, time_flag: bool) -> str:
    if loop_flag and time_flag:
        return "用户在关键页面存在反复回退且停留过长，可能在决策点遇到阻碍（如优惠券不可用）。"
    if loop_flag:
        return "用户路径出现 Loop 异常，存在反复跳转行为，建议检查页面流程与引导文案。"
    if time_flag:
        return "用户停留时长异常偏高，可能出现犹豫或信息理解成本过高的问题。"
    return "未检测到显著异常路径，旅程整体流畅。"


@app.post("/api/v1/logs/ingest")
async def ingest(payload: IngestPayload) -> dict[str, Any]:
    try:
        for event in payload.events:
            if event.event_type != "pointer_move" or not event.coordinates:
                continue

            device_id = event.device_id or "unknown_device"
            viewport_w = event.metadata.get("viewportWidth") or event.metadata.get("viewport_width") or 1
            viewport_h = event.metadata.get("viewportHeight") or event.metadata.get("viewport_height") or 1

            x_norm = max(0.0, min(1.0, float(event.coordinates.x) / max(float(viewport_w), 1.0)))
            y_norm = max(0.0, min(1.0, float(event.coordinates.y) / max(float(viewport_h), 1.0)))

            await pointer_hub.broadcast(
                device_id,
                {
                    "type": "pointer_move",
                    "deviceId": device_id,
                    "userId": event.user_id,
                    "route": event.route,
                    "timestamp": event.timestamp.isoformat(),
                    "x": event.coordinates.x,
                    "y": event.coordinates.y,
                    "xNorm": x_norm,
                    "yNorm": y_norm,
                    "viewport": {"width": viewport_w, "height": viewport_h},
                },
            )

        loop_flag = detect_loop_anomaly(payload.events)
        time_flag = detect_time_anomaly(payload.events)
        summary = summarize_behavior(payload.events, loop_flag, time_flag)

        result = AnomalyResult(
            loop_entropy_anomaly=loop_flag,
            time_threshold_anomaly=time_flag,
            summary=summary,
        )

        return {
            "ok": True,
            "received": len(payload.events),
            "analysis": result.model_dump(),
            "encoding": "utf-8",
            "ts": datetime.utcnow().isoformat() + "Z",
        }
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"ingest_failed: {exc}") from exc


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
