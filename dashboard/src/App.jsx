import { useEffect, useMemo, useRef, useState } from 'react';
import UJMCanvas from '../UJMCanvas.jsx';

const API_BASE = 'http://127.0.0.1:8000';

function toWsBase(apiBase) {
  if (apiBase.startsWith('https://')) {
    return apiBase.replace('https://', 'wss://');
  }
  if (apiBase.startsWith('http://')) {
    return apiBase.replace('http://', 'ws://');
  }
  return apiBase;
}

export default function App() {
  const [selected, setSelected] = useState(null);
  const [deviceId, setDeviceId] = useState('');
  const [deviceList, setDeviceList] = useState([]);
  const [livePointer, setLivePointer] = useState(null);
  const [wsStatus, setWsStatus] = useState('idle');
  const wsRef = useRef(null);

  const journey = useMemo(
    () => ({
      nodes: [
        { id: 'n1', label: '购物车', x: 140, y: 170, anomaly: false },
        { id: 'n2', label: '支付页', x: 360, y: 120, anomaly: true },
        { id: 'n3', label: '优惠券弹窗', x: 600, y: 170, anomaly: true },
        { id: 'n4', label: '返回购物车', x: 360, y: 260, anomaly: true },
      ],
      edges: [
        { source: 'n1', target: 'n2' },
        { source: 'n2', target: 'n3' },
        { source: 'n3', target: 'n4' },
        { source: 'n4', target: 'n2' },
      ],
    }),
    [],
  );

  useEffect(() => {
    let cancelled = false;

    async function fetchDevices() {
      try {
        const resp = await fetch(`${API_BASE}/api/v1/live-pointer/devices`);
        if (!resp.ok) {
          return;
        }
        const json = await resp.json();
        const list = Array.isArray(json.devices) ? json.devices : [];
        if (!cancelled) {
          setDeviceList(list);
          if (!deviceId && list.length > 0) {
            setDeviceId(list[0]);
          }
        }
      } catch {
        // Keep polling and wait for backend readiness.
      }
    }

    fetchDevices();
    const timer = window.setInterval(fetchDevices, 3000);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [deviceId]);

  useEffect(() => {
    if (!deviceId) {
      setWsStatus('idle');
      return undefined;
    }

    setWsStatus('connecting');
    const socket = new WebSocket(`${toWsBase(API_BASE)}/ws/live-pointer/${encodeURIComponent(deviceId)}`);
    wsRef.current = socket;

    socket.onopen = () => {
      setWsStatus('connected');
    };

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data?.type === 'pointer_move') {
          setLivePointer(data);
        }
      } catch {
        // Ignore malformed frames.
      }
    };

    socket.onclose = () => {
      setWsStatus('disconnected');
    };

    socket.onerror = () => {
      setWsStatus('error');
    };

    return () => {
      socket.close();
      wsRef.current = null;
    };
  }, [deviceId]);

  return (
    <main className="mx-auto max-w-6xl p-4 md:p-8">
      <header className="mb-5 rounded-2xl bg-white/75 p-5 shadow-soft backdrop-blur">
        <h1 className="font-display text-2xl font-bold text-ink md:text-3xl">AI-driven UJM Analyzer</h1>
        <p className="mt-2 text-sm text-ink/75 md:text-base">
          异常节点以红色标记；已支持按设备 ID 实时监测某台电脑指针移动。
        </p>
      </header>

      <section className="mb-4 rounded-2xl bg-white/80 p-4 shadow-soft backdrop-blur">
        <h2 className="font-display text-lg font-semibold text-ink">实时设备监控</h2>
        <div className="mt-3 grid gap-3 md:grid-cols-[2fr,1fr,1fr]">
          <label className="text-sm text-ink/80">
            设备 ID
            <input
              className="mt-1 w-full rounded-lg border border-ink/20 bg-white px-3 py-2 text-sm text-ink outline-none ring-0"
              placeholder="device_xxx..."
              value={deviceId}
              onChange={(e) => setDeviceId(e.target.value.trim())}
              list="known-device-ids"
            />
            <datalist id="known-device-ids">
              {deviceList.map((id) => (
                <option key={id} value={id} />
              ))}
            </datalist>
          </label>

          <div className="rounded-lg border border-ink/15 bg-sand/70 px-3 py-2 text-sm text-ink/85">
            <p className="font-semibold">WebSocket 状态</p>
            <p className="mt-1">{wsStatus}</p>
          </div>

          <div className="rounded-lg border border-ink/15 bg-sand/70 px-3 py-2 text-sm text-ink/85">
            <p className="font-semibold">最近坐标</p>
            <p className="mt-1">
              {livePointer ? `${Math.round(livePointer.x)}, ${Math.round(livePointer.y)}` : '暂无'}
            </p>
          </div>
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-[2fr,1fr]">
        <div className="rounded-2xl bg-white/80 p-3 shadow-soft backdrop-blur">
          <UJMCanvas data={journey} onNodeClick={setSelected} livePointer={livePointer} />
        </div>

        <aside className="rounded-2xl bg-ink p-5 text-sand shadow-soft">
          <h2 className="font-display text-lg font-semibold">痛点分析</h2>
          {selected ? (
            <div className="mt-3 space-y-2 text-sm leading-6">
              <p>节点: {selected.label}</p>
              <p>异常: {selected.anomaly ? '是' : '否'}</p>
              <p>
                AI 结论: 用户在支付相关流程中存在反复回退行为，可能由于优惠券校验失败导致决策中断。
              </p>
            </div>
          ) : (
            <p className="mt-3 text-sm text-sand/80">请选择左侧节点查看语义报告。</p>
          )}
        </aside>
      </section>
    </main>
  );
}
