/* eslint-disable no-console */
// Lightweight UJM Tracker SDK (target ~10KB after minify + gzip).

const DEFAULT_CONFIG = {
  endpoint: '/api/v1/logs/ingest',
  flushInterval: 5000,
  maxBuffer: 20,
  appId: 'default-app',
  userId: 'anonymous_user',
  deviceId: null,
  capturePointer: true,
  pointerSampleMs: 120,
  debug: false,
};

const SENSITIVE_KEYWORDS = ['password', 'passwd', 'pwd', 'token', 'secret', 'bank', 'card'];

function nowISO() {
  return new Date().toISOString();
}

function randomId(prefix = 'ujm') {
  return `${prefix}_${Math.random().toString(36).slice(2, 10)}_${Date.now()}`;
}

function getOrCreateDeviceId(explicitDeviceId = null) {
  if (explicitDeviceId) {
    return explicitDeviceId;
  }

  try {
    const storageKey = 'ujm_device_id';
    const existing = window.localStorage.getItem(storageKey);
    if (existing) {
      return existing;
    }
    const created = randomId('device');
    window.localStorage.setItem(storageKey, created);
    return created;
  } catch {
    return randomId('device');
  }
}

function maskCardLike(value) {
  if (typeof value !== 'string') {
    return value;
  }
  return value.replace(/\b\d{12,19}\b/g, '****MASKED_CARD****');
}

function isSensitiveField(name = '') {
  const lower = String(name).toLowerCase();
  return SENSITIVE_KEYWORDS.some((key) => lower.includes(key));
}

function safeSelector(target) {
  if (!(target instanceof Element)) {
    return 'unknown';
  }

  const id = target.id ? `#${target.id}` : '';
  const classes =
    typeof target.className === 'string' && target.className.trim().length > 0
      ? `.${target.className.trim().split(/\s+/).slice(0, 2).join('.')}`
      : '';
  return `${target.tagName.toLowerCase()}${id}${classes}`;
}

function sanitizePayload(payload) {
  try {
    const copy = { ...payload };

    if (copy.elementName && isSensitiveField(copy.elementName)) {
      copy.value = '****MASKED_FIELD****';
    }

    if (copy.inputType === 'password') {
      copy.value = '****MASKED_PASSWORD****';
    }

    if (typeof copy.value === 'string') {
      copy.value = maskCardLike(copy.value).slice(0, 200);
    }

    if (typeof copy.text === 'string') {
      copy.text = maskCardLike(copy.text).slice(0, 200);
    }

    return copy;
  } catch (error) {
    return {
      ...payload,
      value: '****SANITIZE_FAILED****',
      sanitizeError: String(error),
    };
  }
}

class UJMTracker {
  static instance = null;

  static getInstance(config = {}) {
    if (!UJMTracker.instance) {
      UJMTracker.instance = new UJMTracker(config);
    }
    return UJMTracker.instance;
  }

  constructor(config = {}) {
    this.config = { ...DEFAULT_CONFIG, ...config };
    this.sessionId = randomId('session');
    this.deviceId = getOrCreateDeviceId(this.config.deviceId);
    this.buffer = [];
    this.flushTimer = null;
    this.pageEnterAt = Date.now();
    this.lastPointerSampleAt = 0;
    this.started = false;

    this.handleClick = this.handleClick.bind(this);
    this.handleInput = this.handleInput.bind(this);
    this.handleScroll = this.handleScroll.bind(this);
    this.handleRouteChange = this.handleRouteChange.bind(this);
    this.handlePointerMove = this.handlePointerMove.bind(this);
    this.handleVisibility = this.handleVisibility.bind(this);
    this.handleBeforeUnload = this.handleBeforeUnload.bind(this);
  }

  start() {
    if (this.started) {
      return;
    }

    this.started = true;
    document.addEventListener('click', this.handleClick, true);
    document.addEventListener('input', this.handleInput, true);
    document.addEventListener('scroll', this.handleScroll, { passive: true });
    if (this.config.capturePointer) {
      document.addEventListener('mousemove', this.handlePointerMove, { passive: true, capture: true });
    }
    window.addEventListener('popstate', this.handleRouteChange);
    window.addEventListener('hashchange', this.handleRouteChange);
    document.addEventListener('visibilitychange', this.handleVisibility);
    window.addEventListener('beforeunload', this.handleBeforeUnload);

    this.flushTimer = window.setInterval(() => this.flush(), this.config.flushInterval);
    this.logDebug('Tracker started', this.config);
  }

  stop() {
    if (!this.started) {
      return;
    }

    this.started = false;
    document.removeEventListener('click', this.handleClick, true);
    document.removeEventListener('input', this.handleInput, true);
    document.removeEventListener('scroll', this.handleScroll);
    if (this.config.capturePointer) {
      document.removeEventListener('mousemove', this.handlePointerMove, { capture: true });
    }
    window.removeEventListener('popstate', this.handleRouteChange);
    window.removeEventListener('hashchange', this.handleRouteChange);
    document.removeEventListener('visibilitychange', this.handleVisibility);
    window.removeEventListener('beforeunload', this.handleBeforeUnload);

    if (this.flushTimer) {
      window.clearInterval(this.flushTimer);
      this.flushTimer = null;
    }

    this.flush(true);
    this.logDebug('Tracker stopped');
  }

  handleClick(event) {
    try {
      const target = event.target;
      this.enqueue({
        eventType: 'click',
        timestamp: nowISO(),
        pageUrl: location.href,
        route: location.pathname,
        elementId: target?.id || null,
        elementName: target?.getAttribute?.('name') || null,
        selector: safeSelector(target),
        coordinates: { x: event.clientX, y: event.clientY },
        intentLabel: 'interaction',
        text: target?.textContent?.trim()?.slice(0, 100) || null,
      });
    } catch (error) {
      this.logDebug('Click capture failed', error);
    }
  }

  handleInput(event) {
    try {
      const target = event.target;
      if (!(target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement)) {
        return;
      }

      this.enqueue({
        eventType: 'input',
        timestamp: nowISO(),
        pageUrl: location.href,
        route: location.pathname,
        elementId: target.id || null,
        elementName: target.name || null,
        selector: safeSelector(target),
        inputType: target.type || 'text',
        value: target.value || '',
        intentLabel: 'form_fill',
      });
    } catch (error) {
      this.logDebug('Input capture failed', error);
    }
  }

  handleScroll() {
    try {
      this.enqueue({
        eventType: 'scroll',
        timestamp: nowISO(),
        pageUrl: location.href,
        route: location.pathname,
        scrollY: window.scrollY,
        viewportHeight: window.innerHeight,
        intentLabel: 'browse',
      });
    } catch (error) {
      this.logDebug('Scroll capture failed', error);
    }
  }

  handleRouteChange() {
    const dwellMs = Date.now() - this.pageEnterAt;
    this.enqueue({
      eventType: 'route_change',
      timestamp: nowISO(),
      pageUrl: location.href,
      route: location.pathname,
      durationMs: dwellMs,
      intentLabel: 'navigation',
    });
    this.pageEnterAt = Date.now();
  }

  handlePointerMove(event) {
    try {
      const now = Date.now();
      if (now - this.lastPointerSampleAt < this.config.pointerSampleMs) {
        return;
      }
      this.lastPointerSampleAt = now;

      this.enqueue({
        eventType: 'pointer_move',
        timestamp: nowISO(),
        pageUrl: location.href,
        route: location.pathname,
        coordinates: { x: event.clientX, y: event.clientY },
        intentLabel: 'pointer_tracking',
        metadata: {
          viewportWidth: window.innerWidth,
          viewportHeight: window.innerHeight,
        },
      });
    } catch (error) {
      this.logDebug('Pointer capture failed', error);
    }
  }

  handleVisibility() {
    if (document.visibilityState === 'hidden') {
      const dwellMs = Date.now() - this.pageEnterAt;
      this.enqueue({
        eventType: 'dwell',
        timestamp: nowISO(),
        pageUrl: location.href,
        route: location.pathname,
        durationMs: dwellMs,
        intentLabel: 'hesitation_check',
      });
      this.flush(true);
    }
  }

  handleBeforeUnload() {
    const dwellMs = Date.now() - this.pageEnterAt;
    this.enqueue({
      eventType: 'unload',
      timestamp: nowISO(),
      pageUrl: location.href,
      route: location.pathname,
      durationMs: dwellMs,
      intentLabel: 'session_end',
    });
    this.flush(true);
  }

  enqueue(eventData) {
    const sanitized = sanitizePayload({
      ...eventData,
      appId: this.config.appId,
      userId: this.config.userId,
      sessionId: this.sessionId,
      deviceId: this.deviceId,
      userAgent: navigator.userAgent,
      locale: navigator.language,
    });

    this.buffer.push(sanitized);

    if (this.buffer.length >= this.config.maxBuffer) {
      this.flush();
    }
  }

  flush(forceBeacon = false) {
    if (this.buffer.length === 0) {
      return;
    }

    const payload = {
      schemaVersion: '1.0.0',
      encoding: 'utf-8',
      sentAt: nowISO(),
      events: this.buffer.splice(0, this.buffer.length),
    };

    const body = JSON.stringify(payload);

    try {
      if ((forceBeacon || document.visibilityState === 'hidden') && navigator.sendBeacon) {
        const blob = new Blob([body], { type: 'application/json; charset=UTF-8' });
        navigator.sendBeacon(this.config.endpoint, blob);
        return;
      }

      fetch(this.config.endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json; charset=UTF-8',
        },
        body,
        keepalive: true,
      }).catch((error) => {
        this.logDebug('Fetch flush failed', error);
      });
    } catch (error) {
      this.logDebug('Flush failed', error);
    }
  }

  logDebug(message, detail) {
    if (!this.config.debug) {
      return;
    }
    console.debug('[UJMTracker]', message, detail || '');
  }

  getDeviceId() {
    return this.deviceId;
  }
}

export function initUJMTracker(config = {}) {
  const tracker = UJMTracker.getInstance(config);
  tracker.start();
  return tracker;
}

export function getUJMTracker() {
  return UJMTracker.getInstance();
}
