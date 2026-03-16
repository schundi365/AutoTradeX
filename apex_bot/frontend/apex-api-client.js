/**
 * APEX Trading Bot — API Client
 * Connects the frontend dashboard to the FastAPI backend.
 *
 * Usage: included by trading-bot-dashboard.html
 * Config: set APEX_API_BASE before loading this script, e.g.:
 *   <script>window.APEX_API_BASE = "http://localhost:8000";</script>
 */

const APEX = (() => {

  // ── Config ─────────────────────────────────────────
  const BASE    = window.APEX_API_BASE || "http://localhost:8000";
  const WS_BASE = BASE.replace(/^http/, "ws");

  let _ws = null;
  let _wsReconnectTimer = null;
  let _logHandlers   = [];
  let _stateHandlers = [];
  let _connected     = false;

  // ── REST helpers ───────────────────────────────────

  async function get(path) {
    const res = await fetch(`${BASE}${path}`);
    if (!res.ok) throw new Error(`API ${path} → ${res.status}`);
    return res.json();
  }

  async function post(path, body = {}) {
    const res = await fetch(`${BASE}${path}`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`API POST ${path} → ${res.status}`);
    return res.json();
  }

  // ── Public API calls ───────────────────────────────

  const api = {
    status:       ()      => get("/api/status"),
    openTrades:   ()      => get("/api/trades/open"),
    tradeHistory: (n=100) => get(`/api/trades/history?limit=${n}`),
    analytics:    ()      => get("/api/analytics"),
    news:         (n=20)  => get(`/api/news?limit=${n}`),
    calendar:     ()      => get("/api/calendar"),
    config:       ()      => get("/api/config"),
    updateConfig: (body)  => post("/api/config", body),
    startBot:     ()      => post("/api/bot/start"),
    stopBot:      ()      => post("/api/bot/stop"),
    restartBot:   ()      => post("/api/bot/restart"),
  };

  // ── WebSocket live stream ──────────────────────────

  function connectWS() {
    if (_ws && _ws.readyState <= 1) return;

    _ws = new WebSocket(`${WS_BASE}/ws`);

    _ws.onopen = () => {
      _connected = true;
      clearTimeout(_wsReconnectTimer);
      console.log("[APEX WS] Connected →", WS_BASE);
      _updateConnectionBadge(true);
      setInterval(() => {
        if (_ws.readyState === 1)
          _ws.send(JSON.stringify({ type: "ping" }));
      }, 20_000);
    };

    _ws.onmessage = (evt) => {
      try {
        const msg = JSON.parse(evt.data);
        if (msg.type === "log")          _logHandlers.forEach(h => h(msg));
        if (msg.type === "state_update") _stateHandlers.forEach(h => h(msg));
      } catch (e) { /* ignore */ }
    };

    _ws.onclose = () => {
      _connected = false;
      _updateConnectionBadge(false);
      console.warn("[APEX WS] Disconnected — reconnecting in 3s…");
      _wsReconnectTimer = setTimeout(connectWS, 3000);
    };

    _ws.onerror = (e) => console.error("[APEX WS] Error:", e);
  }

  function onLog(handler)   { _logHandlers.push(handler); }
  function onState(handler) { _stateHandlers.push(handler); }

  // ── Connection badge ───────────────────────────────

  function _updateConnectionBadge(online) {
    document.querySelectorAll(".status-dot.live").forEach(d => {
      d.style.background = online ? "var(--accent-green)" : "var(--accent-red)";
      d.style.boxShadow  = online
        ? "0 0 8px var(--accent-green)"
        : "0 0 8px var(--accent-red)";
    });
  }

  // ── Dashboard data loaders ─────────────────────────

  async function loadStatus() {
    try {
      const data = await api.status();
      const runDot = document.querySelector(".status-dot.live");
      if (runDot) {
        runDot.style.background = data.bot_running
          ? "var(--accent-green)" : "var(--text-muted)";
      }
      if (data.account) {
        const balEl = document.querySelector("[data-metric='balance']");
        if (balEl) balEl.textContent = `$${Number(data.account.balance).toLocaleString()}`;
      }
      return data;
    } catch (e) { console.warn("loadStatus:", e.message); }
  }

  async function loadOpenTrades() {
    try {
      const data = await api.openTrades();
      const tbody = document.getElementById("openTradesBody");
      if (tbody && data.trades) {
        tbody.innerHTML = data.trades.map(t => {
          const pnlCls = t.pnl >= 0 ? "pos" : "neg";
          const pnlStr = (t.pnl >= 0 ? "+$" : "-$") + Math.abs(t.pnl).toFixed(2);
          return `
            <tr>
              <td><span class="trade-sym">${t.symbol}</span>
                  <div style="font-size:9px;color:var(--text-muted)">${t.asset_class}·${t.broker}</div></td>
              <td><span class="direction-badge ${t.direction==="BUY"?"buy":"sell"}">${t.direction}</span></td>
              <td>${t.lot_size}</td>
              <td>${_fmt(t.entry_price)}</td>
              <td style="color:${t.pnl>=0?"var(--accent-green)":"var(--accent-red)"}">${_fmt(t.current_price||t.entry_price)}</td>
              <td style="color:var(--accent-red)">${_fmt(t.stop_loss)}</td>
              <td style="color:var(--accent-green)">${_fmt(t.take_profit)}</td>
              <td class="pnl ${pnlCls}">${pnlStr}</td>
              <td>${_duration(t.open_time)}</td>
              <td><span class="status-tag open">OPEN</span></td>
            </tr>`;
        }).join("");
      }
      const kpiOpen = document.querySelector("[data-kpi='open_trades']");
      if (kpiOpen) kpiOpen.textContent = data.count;
      const kpiPnl = document.querySelector("[data-kpi='open_pnl']");
      if (kpiPnl) {
        const t = data.total_pnl || 0;
        kpiPnl.textContent = (t>=0?"+$":"-$") + Math.abs(t).toFixed(2);
        kpiPnl.style.color = t>=0 ? "var(--accent-green)" : "var(--accent-red)";
      }
    } catch (e) { console.warn("loadOpenTrades:", e.message); }
  }

  async function loadAnalytics() {
    try {
      const data = await api.analytics();
      const kpis = {
        "total_pnl":     `+$${data.total_pnl?.toLocaleString()}`,
        "win_rate":      `${((data.win_rate||0)*100).toFixed(1)}%`,
        "sharpe_ratio":  data.sharpe_ratio?.toFixed(2),
        "max_drawdown":  `-${((data.max_drawdown||0)*100).toFixed(1)}%`,
        "profit_factor": data.profit_factor?.toFixed(2),
      };
      Object.entries(kpis).forEach(([k,v]) => {
        const el = document.querySelector(`[data-kpi='${k}']`);
        if (el) el.textContent = v;
      });
      if (data.by_asset_class) {
        Object.entries(data.by_asset_class).forEach(([cls,stats]) => {
          const bar = document.querySelector(`[data-asset-bar='${cls}']`);
          const lbl = document.querySelector(`[data-asset-wr='${cls}']`);
          if (bar) bar.style.width = `${((stats.win_rate||0)*100).toFixed(0)}%`;
          if (lbl) lbl.textContent = `${((stats.win_rate||0)*100).toFixed(1)}% win`;
        });
      }
      return data;
    } catch (e) { console.warn("loadAnalytics:", e.message); }
  }

  async function loadNews() {
    try {
      const data = await api.news(10);
      const container = document.getElementById("newsFeed");
      if (!container || !data.items) return;
      container.innerHTML = data.items.map(item => {
        const catCls = item.categories?.includes("geopolitical") ? "geo"
                     : item.impact === "HIGH" ? "eco" : "mkt";
        const catLbl = item.categories?.includes("geopolitical") ? "GEO-POL"
                     : item.impact === "HIGH" ? "ECONOMIC" : "MARKET";
        const time = new Date(item.published)
          .toLocaleTimeString("en-GB",{hour:"2-digit",minute:"2-digit"}) + " UTC";
        return `
          <div class="news-item">
            <div class="news-meta">
              <span class="news-cat ${catCls}">${catLbl}</span>
              <span class="news-time">${time}</span>
            </div>
            <div class="news-title">${item.title}</div>
            <div class="news-impact">${_impactDots(item.impact)}</div>
          </div>`;
      }).join("");
    } catch (e) { console.warn("loadNews:", e.message); }
  }

  async function loadCalendar() {
    try {
      const data = await api.calendar();
      const tbody = document.getElementById("calendarBody");
      if (!tbody || !data.events) return;
      tbody.innerHTML = data.events.map(ev => {
        const t = new Date(ev.scheduled)
          .toLocaleTimeString("en-GB",{hour:"2-digit",minute:"2-digit"});
        const actionCls = ev.impact==="HIGH"
          ? "var(--accent-red)" : "var(--accent-amber)";
        const actionTxt = ev.impact==="HIGH"
          ? "⛔ PAUSE TRADING" : "⚠ TIGHTEN SL";
        return `
          <tr>
            <td style="color:var(--accent-amber)">${t}</td>
            <td><b>${ev.title}</b></td>
            <td>${ev.currency}</td>
            <td>${_impactDots(ev.impact)}</td>
            <td>${ev.previous||"—"}</td>
            <td>${ev.forecast||"—"}</td>
            <td><span style="color:${actionCls};font-size:10px">${actionTxt}</span></td>
          </tr>`;
      }).join("");
    } catch (e) { console.warn("loadCalendar:", e.message); }
  }

  async function loadConfig() {
    try {
      const data = await api.config();
      if (data.risk) {
        const rs = document.getElementById("riskSlider");
        if (rs) { rs.value = data.risk.max_risk_per_trade_pct||1.5;
                  document.getElementById("riskVal").textContent = rs.value+"%"; }
        const dd = document.getElementById("ddSlider");
        if (dd) { dd.value = data.risk.max_daily_drawdown_pct||5;
                  document.getElementById("ddVal").textContent = dd.value+"%"; }
      }
    } catch (e) { console.warn("loadConfig:", e.message); }
  }

  async function loadTradeHistory() {
    try {
      const data = await api.tradeHistory(50);
      const tbody = document.getElementById("tradeHistoryBody");
      if (!tbody || !data.trades) return;
      tbody.innerHTML = data.trades.map(t => `
        <tr>
          <td>${new Date(t.open_time).toLocaleString()}</td>
          <td><span class="trade-sym" style="font-size:13px">${t.symbol}</span></td>
          <td><span class="direction-badge ${t.direction==="BUY"?"buy":"sell"}">${t.direction}</span></td>
          <td>${_fmt(t.entry_price)}</td>
          <td>${_fmt(t.close_price)}</td>
          <td class="pnl ${t.pnl>=0?"pos":"neg"}">${(t.pnl>=0?"+$":"-$")+Math.abs(t.pnl).toFixed(2)}</td>
          <td style="color:var(--text-secondary);font-size:10px">${(t.strategy||"").toUpperCase()}</td>
          <td><span class="status-tag closed">CLOSED</span></td>
        </tr>`).join("");
    } catch (e) { console.warn("loadTradeHistory:", e.message); }
  }

  // ── Live log injection ─────────────────────────────

  function injectLogLine(msg) {
    const container = document.getElementById("logContainer");
    if (!container) return;
    const div = document.createElement("div");
    div.className = "log-line";
    div.innerHTML = `
      <span class="log-time">${msg.time}</span>
      <span class="log-level ${msg.level}">${msg.level}</span>
      <span class="log-msg">${msg.msg}</span>`;
    container.insertBefore(div, container.firstChild);
    while (container.children.length > 300)
      container.removeChild(container.lastChild);
  }

  // ── Bot controls ───────────────────────────────────

  async function startBot() {
    try { await api.startBot(); console.log("[APEX] Bot started"); }
    catch (e) { alert("Start failed: " + e.message); }
  }

  async function stopBot() {
    try { await api.stopBot(); console.log("[APEX] Bot stopped"); }
    catch (e) { alert("Stop failed: " + e.message); }
  }

  async function restartBot() {
    if (!confirm("Restart bot? Existing trades are unaffected.")) return;
    try { await api.restartBot(); }
    catch (e) { alert("Restart failed: " + e.message); }
  }

  async function saveConfig(payload) {
    try { await api.updateConfig(payload); return true; }
    catch (e) { alert("Save failed: " + e.message); return false; }
  }

  // ── Auto-refresh ───────────────────────────────────

  function startAutoRefresh() {
    loadStatus(); loadOpenTrades(); loadNews();
    setInterval(() => { loadStatus(); loadOpenTrades(); }, 10_000);
    setInterval(() => { loadNews(); loadCalendar(); }, 60_000);
  }

  // ── Init ───────────────────────────────────────────

  function init() {
    connectWS();
    onLog(injectLogLine);
    onState(msg => {
      const el = document.querySelector("[data-kpi='open_trades']");
      if (el && msg.open_trades !== undefined) el.textContent = msg.open_trades;
    });
    startAutoRefresh();
    loadAnalytics();
    loadCalendar();
    loadConfig();
    console.log("[APEX] Dashboard ready → backend:", BASE);
  }

  // ── Helpers ────────────────────────────────────────

  function _fmt(v) {
    const n = parseFloat(v);
    if (isNaN(n)) return "—";
    return n > 1000
      ? n.toLocaleString(undefined,{maximumFractionDigits:2})
      : n.toFixed(5);
  }

  function _duration(iso) {
    if (!iso) return "—";
    const ms = Date.now() - new Date(iso).getTime();
    return `${Math.floor(ms/3_600_000)}h ${Math.floor((ms%3_600_000)/60_000)}m`;
  }

  function _impactDots(impact) {
    const n = {HIGH:3,MEDIUM:2,LOW:1}[impact]||1;
    return [1,2,3].map(i =>
      `<div class="impact-dot ${i<=n?"filled high":"empty"}"></div>`
    ).join("");
  }

  return {
    init, api, onLog, onState,
    loadStatus, loadOpenTrades, loadAnalytics,
    loadNews, loadCalendar, loadConfig, loadTradeHistory,
    startBot, stopBot, restartBot, saveConfig,
  };
})();

if (document.readyState === "loading")
  document.addEventListener("DOMContentLoaded", APEX.init);
else
  APEX.init();
