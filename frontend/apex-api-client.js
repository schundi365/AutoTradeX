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
  const BASE = window.APEX_API_BASE || window.location.origin;
  const WS_BASE = BASE.replace(/^http/, "ws");

  let _ws = null;
  let _wsReconnectTimer = null;
  let _wsPingTimer = null;        // stored so it can be cleared on reconnect
  let _logHandlers = [];
  let _stateHandlers = [];
  let _connected = false;

  // ── REST helpers ───────────────────────────────────

  async function get(path) {
    const res = await fetch(`${BASE}${path}`);
    if (!res.ok) throw new Error(`API ${path} → ${res.status}`);
    return res.json();
  }

  async function post(path, body = {}) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 10000); // 10 second timeout
    
    try {
      const res = await fetch(`${BASE}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: controller.signal
      });
      clearTimeout(timeoutId);
      if (!res.ok) throw new Error(`API POST ${path} → ${res.status}`);
      return res.json();
    } catch (error) {
      clearTimeout(timeoutId);
      if (error.name === 'AbortError') {
        throw new Error(`Request timeout after 10 seconds`);
      }
      throw error;
    }
  }

  // ── Public API calls ───────────────────────────────

  const api = {
    status: () => get("/api/status"),
    openTrades: () => get("/api/trades/open"),
    tradeHistory: (n = 100) => get(`/api/trades/history?limit=${n}`),
    decisionHistory: (n = 50) => get(`/api/decisions?limit=${n}`),
    analytics: () => get("/api/analytics"),
    news: (n = 20) => get(`/api/news?limit=${n}`),
    calendar: () => get("/api/calendar"),
    config: () => get("/api/config"),
    apexHealth: () => get("/api/ai/apex-health"),
    updateConfig: (body) => post("/api/config", body),
    startBot: () => post("/api/bot/start"),
    stopBot: () => post("/api/bot/stop"),
    restartBot: () => post("/api/bot/restart"),
  };

  // ── WebSocket live stream ──────────────────────────

  function connectWS() {
    if (_ws && _ws.readyState <= 1) return;

    _ws = new WebSocket(`${WS_BASE}/ws`);

    _ws.onopen = () => {
      _connected = true;
      clearTimeout(_wsReconnectTimer);
      // Clear any previous ping timer to avoid accumulating timers on reconnect
      if (_wsPingTimer) clearInterval(_wsPingTimer);
      console.log("[APEX WS] Connected →", WS_BASE);
      _updateConnectionBadge(true);
      _wsPingTimer = setInterval(() => {
        if (_ws && _ws.readyState === 1)
          _ws.send(JSON.stringify({ type: "ping" }));
      }, 20_000);
    };

    _ws.onmessage = (evt) => {
      try {
        const msg = JSON.parse(evt.data);
        if (msg.type === "log") _logHandlers.forEach(h => h(msg));
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

  function onLog(handler) { _logHandlers.push(handler); }
  function onState(handler) { _stateHandlers.push(handler); }

  // ── Connection badge ───────────────────────────────

  function _updateConnectionBadge(online) {
    document.querySelectorAll(".status-dot.live").forEach(d => {
      d.style.background = online ? "var(--accent-green)" : "var(--accent-red)";
      d.style.boxShadow = online
        ? "0 0 8px var(--accent-green)"
        : "0 0 8px var(--accent-red)";
    });
  }

  // ── Dashboard data loaders ─────────────────────────

  // Currency symbol for the account — defaults to $ until status loaded
  let _acctCurrency = "$";
  function _pnl(v) {
    const sym = _acctCurrency;
    return (v >= 0 ? "+" : "-") + sym + Math.abs(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  async function loadStatus() {
    try {
      const data = await api.status();

      // Store account currency for use in all P&L formatting
      if (data.account?.currency) _acctCurrency = data.account.currency === "USD" ? "$"
        : data.account.currency === "EUR" ? "€"
          : data.account.currency === "GBP" ? "£"
            : data.account.currency;

      // Update running status dot
      const runDot = document.querySelector(".status-dot.live");
      if (runDot) {
        runDot.style.background = data.bot_running
          ? "var(--accent-green)" : "var(--text-muted)";
      }

      // Update active agents badge
      const activeBadge = document.querySelector("[data-kpi='active_agents']");
      if (activeBadge) {
        activeBadge.textContent = data.bot_running ? "6 ACTIVE" : "OFFLINE";
        activeBadge.style.background = data.bot_running ? "rgba(0,230,118,0.15)" : "rgba(255,61,90,0.15)";
      }

      // Update Account Balance
      if (data.account) {
        const balEl = document.querySelector("[data-metric='balance']");
        if (balEl) balEl.textContent = _acctCurrency + Number(data.account.balance).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        // Update equity in sidebar if present
        const eqEl = document.querySelector("[data-metric='equity']");
        if (eqEl) eqEl.textContent = _acctCurrency + Number(data.account.equity).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
      }

      // Update Dashboard KPIs from Performance object
      if (data.performance) {
        const p = data.performance;
        const kpis = {
          "total_pnl": _pnl(p.total_pnl || 0),
          "win_rate": `${((p.win_rate || 0) * 100).toFixed(1)}%`,
          "sharpe_ratio": (p.sharpe_ratio || 0).toFixed(2),
          "max_drawdown": `-${_acctCurrency}${Math.abs(p.max_drawdown || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
          "current_drawdown": `-${_acctCurrency}${Math.abs(p.current_drawdown || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
          "profit_factor": (p.profit_factor || 0).toFixed(2),
          "today_pnl": _pnl(p.today_pnl || p.total_pnl || 0),
          "trade_stats": `${p.total_trades || 0} trades`,
        };

        Object.entries(kpis).forEach(([k, v]) => {
          document.querySelectorAll(`[data-kpi='${k}']`).forEach(el => {
            el.textContent = v;
            if (k.includes("pnl")) {
              const val = k === "today_pnl" ? (p.today_pnl ?? p.total_pnl ?? 0) : (p.total_pnl || 0);
              el.style.color = val >= 0 ? "var(--accent-green)" : "var(--accent-red)";
            }
          });
        });
      }

      // Populate Agent List
      const agentList = document.getElementById("agentList");
      if (agentList) {
        const agents = [
          { name: "Orchestrator", icon: "🔮", color: "245,166,35", task: data.bot_running ? "Monitoring market conditions..." : "Idle" },
          { name: "Strategy Adapter", icon: "🧠", color: "120,80,255", task: data.bot_running ? "Adapting regime profile & watchdog..." : "Idle" },
          { name: "Market Analyst", icon: "📊", color: "0,230,118", task: data.bot_running ? "Analyzing price action..." : "Idle" },
          { name: "Correlation Manager", icon: "📐", color: "80,200,255", task: data.bot_running ? "Checking correlations & divergence..." : "Idle" },
          { name: "Sentiment Agent", icon: "📰", color: "0,180,255", task: data.bot_running ? "Processing news feed..." : "Idle" },
          { name: "Calendar Agent", icon: "📅", color: "157,78,221", task: data.bot_running ? "Checking economic events..." : "Idle" },
          { name: "Risk Manager", icon: "🛡️", color: "255,61,90", task: data.bot_running ? "Validating exposures..." : "Idle" },
          { name: "Execution Agent", icon: "⚡", color: "245,166,35", task: data.bot_running ? "Ready for signals" : "Offline" },
        ];
        agentList.innerHTML = agents.map(a => `
          <div class="agent-row">
            <div class="agent-icon" style="background:rgba(${a.color},0.1)">${a.icon}</div>
            <div class="agent-info">
              <div class="agent-name">${a.name}</div>
              <div class="agent-task">${a.task}</div>
            </div>
            <div class="agent-status-dot ${data.bot_running ? 'active' : 'idle'}"></div>
          </div>
        `).join("");
      }

      return data;
    } catch (e) { console.warn("loadStatus:", e.message); }
  }

  async function loadOpenTrades() {
    try {
      const data = await api.openTrades();
      const tbody = document.getElementById("openTradesBody");
      if (tbody && data.trades) {
        tbody.innerHTML = data.trades.length === 0
          ? `<tr><td colspan="10" style="text-align:center;color:var(--text-muted);padding:24px">No open positions</td></tr>`
          : data.trades.map(t => {
            const pnlCls = t.pnl >= 0 ? "pos" : "neg";
            const pnlStr = (t.pnl >= 0 ? "+$" : "-$") + Math.abs(t.pnl || 0).toFixed(2);
            const pnlColor = t.pnl >= 0 ? "var(--accent-green)" : "var(--accent-red)";
            const ticket = t.broker_order_id || t.id || "";
            return `
            <tr data-symbol="${(t.symbol || "").toUpperCase()}" title="Ticket: ${ticket}">
              <td><span class="trade-sym">${t.symbol}</span>
                  <div style="font-size:9px;color:var(--text-muted)">${t.asset_class || "FOREX"}·${t.broker || "MT5"}</div></td>
              <td><span class="direction-badge ${t.direction === "BUY" ? "buy" : "sell"}">${t.direction}</span></td>
              <td>${(t.lot_size || 0).toFixed(2)}</td>
              <td>${_fmt(t.entry_price)}</td>
              <td style="color:${pnlColor}">${_fmt(t.current_price || t.entry_price)}</td>
              <td style="color:var(--accent-red)">${_fmt(t.stop_loss)}</td>
              <td style="color:var(--accent-green)">${_fmt(t.take_profit)}</td>
              <td class="pnl ${pnlCls}" style="color:${pnlColor}">${pnlStr}</td>
              <td>${_duration(t.open_time)}</td>
              <td><span class="status-tag open">OPEN</span></td>
            </tr>`;
          }).join("");
      }
      document.querySelectorAll("[data-kpi='open_trades']").forEach(el => {
        el.textContent = data.count;
      });

      const t = data.total_pnl || 0;
      document.querySelectorAll("[data-kpi='open_pnl']").forEach(el => {
        el.textContent = _pnl(t);
        el.style.color = t >= 0 ? "var(--accent-green)" : "var(--accent-red)";
      });

      // Update sidebar asset-class count badges from live open positions
      if (data.trades) {
        const counts = {};
        data.trades.forEach(tr => {
          const ac = (tr.asset_class || "FOREX").toUpperCase();
          counts[ac] = (counts[ac] || 0) + 1;
        });
        // Update counts that aren't already driven by analytics
        Object.entries(counts).forEach(([ac, cnt]) => {
          document.querySelectorAll(`[data-asset-wr-count='${ac}']`).forEach(el => {
            const existing = parseInt(el.textContent || "0", 10);
            if (existing === 0) el.textContent = cnt;  // only fill if analytics hasn't set it
          });
        });
        document.querySelectorAll("[data-kpi='total_assets']").forEach(el => {
          if (el.textContent === "0") el.textContent = data.count;
        });
      }
    } catch (e) { console.warn("loadOpenTrades:", e.message); }
  }

  async function loadAnalytics() {
    try {
      const data = await api.analytics();
      const kpis = {
        "total_pnl": _pnl(data.total_pnl || 0),
        "win_rate": `${((data.win_rate || 0) * 100).toFixed(1)}%`,
        "sharpe_ratio": (data.sharpe_ratio || 0).toFixed(2),
        "max_drawdown": `-${_acctCurrency}${Math.abs(data.max_drawdown || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
        "current_drawdown": `-${_acctCurrency}${Math.abs(data.current_drawdown || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
        "profit_factor": (data.profit_factor || 0).toFixed(2),
        "today_pnl": _pnl(data.today_pnl || 0),
        "trade_stats": `${data.total_trades || 0} trades total`,
        "open_pnl": _pnl(data.open_pnl || 0),
      };

      Object.entries(kpis).forEach(([k, v]) => {
        document.querySelectorAll(`[data-kpi='${k}']`).forEach(el => {
          el.textContent = v;
          if (k.includes("pnl")) {
            const val = k === "today_pnl" ? (data.today_pnl || 0) : k === "open_pnl" ? (data.open_pnl || 0) : (data.total_pnl || 0);
            el.style.color = val >= 0 ? "var(--accent-green)" : "var(--accent-red)";
          }
        });
      });

      // Asset class bars + sidebar badges
      if (data.by_asset_class) {
        let totalAssets = 0;
        Object.entries(data.by_asset_class).forEach(([cls, stats]) => {
          const c = cls.toUpperCase();
          const wr = ((stats.win_rate || 0) * 100).toFixed(1);
          const cnt = stats.count || 0;
          totalAssets += cnt;
          document.querySelectorAll(`[data-asset-bar='${c}']`).forEach(el => el.style.width = `${wr}%`);
          document.querySelectorAll(`[data-asset-wr='${c}']`).forEach(el => el.textContent = `${wr}% win`);
          document.querySelectorAll(`[data-asset-wr-count='${c}']`).forEach(el => el.textContent = cnt);
        });
        document.querySelectorAll(`[data-kpi='total_assets']`).forEach(el => el.textContent = totalAssets || data.total_trades || 0);
      }

      if (data.by_strategy) {
        Object.entries(data.by_strategy).forEach(([strat, stats]) => {
          const s = strat.toUpperCase().replace(/\s+/g, "_");
          const pnlStr = _pnl(stats.pnl || 0);
          const wr = ((stats.win_rate || 0) * 100).toFixed(0);
          document.querySelectorAll(`[data-strat-pnl='${s}']`).forEach(el => el.textContent = `${pnlStr} · ${wr}% WR`);
          document.querySelectorAll(`[data-strat-bar='${s}']`).forEach(el => el.style.width = `${wr}%`);
        });
      }

      // Equity curve from API data (used when no closed trade objects available locally)
      if (data.equity_curve && data.equity_curve.length > 1) {
        _drawEquityCurveFromPoints(data.equity_curve);
      }

      return data;
    } catch (e) { console.warn("loadAnalytics:", e.message); }
  }

  function _drawEquityCurveFromPoints(points) {
    const pathEl = document.getElementById("equityCurvePath");
    const fillEl = document.getElementById("equityCurveFill");
    const dotEl = document.getElementById("equityCurveDot");
    if (!pathEl || points.length < 2) return;
    const vals = points.map(p => p.equity);
    const min = Math.min(...vals, 0);
    const max = Math.max(...vals, 1);
    const range = max - min || 1;
    const w = 600, h = 180, pad = 20;
    const pts = vals.map((v, i) => ({
      x: (i / (vals.length - 1)) * w,
      y: h - pad - ((v - min) / range) * (h - 2 * pad),
    }));
    const d = "M" + pts.map(p => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" L");
    pathEl.setAttribute("d", d);
    if (fillEl) fillEl.setAttribute("d", d + ` L${w},${h} L0,${h} Z`);
    if (dotEl) { dotEl.setAttribute("cx", pts[pts.length - 1].x); dotEl.setAttribute("cy", pts[pts.length - 1].y); }
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
          .toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" }) + " UTC";
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
          .toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
        const actionCls = ev.impact === "HIGH"
          ? "var(--accent-red)" : "var(--accent-amber)";
        const actionTxt = ev.impact === "HIGH"
          ? "⛔ PAUSE TRADING" : "⚠ TIGHTEN SL";
        return `
          <tr>
            <td style="color:var(--accent-amber)">${t}</td>
            <td><b>${ev.title}</b></td>
            <td>${ev.currency}</td>
            <td>${_impactDots(ev.impact)}</td>
            <td>${ev.previous || "—"}</td>
            <td>${ev.forecast || "—"}</td>
            <td><span style="color:${actionCls};font-size:10px">${actionTxt}</span></td>
          </tr>`;
      }).join("");
    } catch (e) { console.warn("loadCalendar:", e.message); }
  }

  async function loadConfig() {
    try {
      const data = await api.config();
      if (!data.risk) return;
      const r = data.risk;

      function _setSlider(id, valId, value, suffix) {
        const el = document.getElementById(id);
        if (!el) return;
        el.value = value;
        const disp = document.getElementById(valId);
        if (disp) disp.textContent = value + (suffix || "");
      }
      function _setInput(id, value) {
        const el = document.getElementById(id);
        if (el) el.value = value;
      }

      // SOP §06 — hard limits
      _setSlider("riskSlider", "riskVal", r.max_risk_per_trade_pct ?? 2.0, "%");
      _setSlider("combinedRiskSlider", "combinedRiskVal", r.max_combined_risk_pct ?? 6.0, "%");
      _setSlider("ddSlider", "ddVal", r.max_daily_drawdown_pct ?? 2.0, "%");
      _setSlider("tradesSlider", "tradesVal", r.max_open_trades ?? 10, "");
      _setSlider("symTradesSlider", "symTradesVal", r.max_trades_per_symbol ?? 2, "");
      _setSlider("consecLossSlider", "consecLossVal", r.max_consecutive_losses ?? 5, "");
      _setSlider("equityFloorSlider", "equityFloorVal", r.min_equity_pct ?? 70, "%");
      _setSlider("ddScaleSlider", "ddScaleVal", r.drawdown_scale_threshold_pct ?? 5, "%");
      _setInput("maxLotInput", r.max_lot_size ?? 2.0);
      _setInput("posMgmtIntervalInput", r.position_mgmt_interval_sec ?? 15);

      // SOP §01 — signal gates
      _setSlider("minScoreSlider", "minScoreVal", r.min_signal_score ?? 6.5, "");
      // confidence stored as 0-1; display as %
      _setSlider("minConfSlider", "minConfVal", Math.round((r.min_confidence ?? 0.6) * 100), "%");
      _setSlider("minRRSlider", "minRRVal", r.min_risk_reward ?? 1.8, ":1");
      _setSlider("minAdxSlider", "minAdxVal", r.min_adx ?? 18, "");
      _setInput("minAtrRatioInput", r.min_atr_ratio ?? 0.5);
      _setInput("maxAtrRatioInput", r.max_atr_ratio ?? 2.0);
      _setSlider("minVolRatioSlider", "minVolRatioVal", r.min_volume_ratio ?? 0.8, "×");

      // Calendar blackout
      _setSlider("pauseBeforeSlider", "pauseBeforeVal", r.blackout_before_high_impact ?? 15, "m");
      _setSlider("pauseAfterSlider", "pauseAfterVal", r.blackout_after_high_impact ?? 30, "m");

      // Strategy
      if (data.strategy) {
        _setSlider("sentSlider", "sentVal", data.strategy.sentiment_threshold ?? 0.65, "");
        // Timeframes
        const tfSelect = document.getElementById('cfg-timeframes');
        if (tfSelect && data.strategy.timeframes) {
          Array.from(tfSelect.options).forEach(opt => {
            opt.selected = data.strategy.timeframes.includes(opt.value);
          });
        }
      }

      // AI model names
      if (data.ai) {
        _setInput("cfg-ollama-model", data.ai.ollama_model ?? "apex-trader");
      }
    } catch (e) { console.warn("loadConfig:", e.message); }
  }

  function drawEquityChart(trades) {
    const pathEl = document.getElementById("equityCurvePath");
    const fillEl = document.getElementById("equityCurveFill");
    const dotEl = document.getElementById("equityCurveDot");
    if (!pathEl || !trades || trades.length < 2) return;

    // Sort by time
    const sorted = [...trades].sort((a, b) => new Date(a.close_time) - new Date(b.close_time));

    // Cumulative P&L
    let sum = 0;
    const history = sorted.map(t => {
      sum += (t.pnl || 0);
      return sum;
    });
    history.unshift(0); // Start at 0

    const min = Math.min(...history, 0);
    const max = Math.max(...history, 10);
    const range = max - min || 1;

    const w = 600;
    const h = 180;
    const padding = 20;

    const points = history.map((val, i) => {
      const x = (i / (history.length - 1)) * w;
      const y = h - padding - ((val - min) / range) * (h - 2 * padding);
      return { x, y };
    });

    const d = "M" + points.map(p => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" L");
    pathEl.setAttribute("d", d);

    // Fill path (closes back to bottom)
    const fillD = d + ` L${w},${h} L0,${h} Z`;
    fillEl.setAttribute("d", fillD);

    // Last point dot
    const last = points[points.length - 1];
    dotEl.setAttribute("cx", last.x);
    dotEl.setAttribute("cy", last.y);
  }

  async function loadTradeHistory() {
    try {
      const data = await api.tradeHistory(50);
      const tbody = document.getElementById("tradeHistoryBody");
      const rbody = document.getElementById("recentTradesBody");
      if (!data.trades) return;

      // Update history badge count
      const histBadge = tbody?.closest(".sec-card")?.querySelector(".sec-badge");
      if (histBadge) histBadge.textContent = `${data.total || data.trades.length} TRADES`;

      const histRows = data.trades.length === 0
        ? `<tr><td colspan="8" style="text-align:center;color:var(--text-muted);padding:24px">No trade history</td></tr>`
        : data.trades.map(t => `
        <tr data-symbol="${(t.symbol || "").toUpperCase()}">
          <td>${new Date(t.open_time).toLocaleString()}</td>
          <td><span class="trade-sym" style="font-size:13px">${t.symbol}</span></td>
          <td><span class="direction-badge ${t.direction === "BUY" ? "buy" : "sell"}">${t.direction}</span></td>
          <td>${_fmt(t.entry_price)}</td>
          <td>${_fmt(t.close_price)}</td>
          <td class="pnl ${t.pnl >= 0 ? "pos" : "neg"}">${_pnl(t.pnl || 0)}</td>
          <td style="color:var(--text-secondary);font-size:10px">${(t.strategy || "").toUpperCase()}</td>
          <td><span class="status-tag closed">CLOSED</span></td>
        </tr>`).join("");

      if (tbody) tbody.innerHTML = histRows;

      // Recent trades panel on overview — show last 5 open+closed combined
      if (rbody) {
        rbody.innerHTML = data.trades.length === 0
          ? `<tr><td colspan="5" style="text-align:center;color:var(--text-muted);padding:16px">No recent trades</td></tr>`
          : data.trades.slice(0, 5).map(t => `
          <tr data-symbol="${(t.symbol || "").toUpperCase()}">
            <td><span class="trade-sym" style="font-size:12px">${t.symbol}</span></td>
            <td><span class="direction-badge ${t.direction === "BUY" ? "buy" : "sell"}" style="font-size:9px">${t.direction}</span></td>
            <td>${_fmt(t.entry_price)}</td>
            <td class="pnl ${t.pnl >= 0 ? "pos" : "neg"}">${_pnl(t.pnl || 0)}</td>
            <td><span class="status-tag closed">CLOSED</span></td>
          </tr>`).join("");
      }

      // Update Equity Chart
      drawEquityChart(data.trades);

    } catch (e) { console.warn("loadTradeHistory:", e.message); }
  }

  async function loadDecisionHistory() {
    try {
      const data = await api.decisionHistory(50);
      const tbody = document.getElementById("decisionHistoryBody");
      if (!tbody) return;

      // Update badge count
      const badge = document.getElementById("decisionHistoryBadge");
      if (badge && data.decisions) {
        badge.textContent = `${data.decisions.length} DECISIONS`;
      }

      if (!data.decisions || data.decisions.length === 0) {
        tbody.innerHTML = `<tr><td colspan="8" style="text-align:center;color:var(--text-muted);padding:24px">No decision history available</td></tr>`;
        return;
      }

      tbody.innerHTML = data.decisions.map(d => {
        const timestamp = new Date(d.timestamp).toLocaleString();
        const decisionClass = d.decision === 'GO' ? 'executed' 
          : d.decision === 'NOGO' ? 'rejected' 
          : d.decision === 'EXECUTED' ? 'executed' 
          : d.decision === 'SKIPPED' ? 'skipped' 
          : d.decision === 'REJECTED' ? 'rejected' 
          : d.decision === 'APPROVE' ? 'executed'
          : d.decision === 'REJECT' ? 'rejected'
          : 'pending';
        
        const decisionDisplay = d.decision === 'GO' ? 'APPROVED' 
          : d.decision === 'NOGO' ? 'REJECTED' 
          : d.decision;

        const confidence = d.confidence ? `${(d.confidence * 100).toFixed(0)}%` : '--';
        const confidenceClass = d.confidence >= 0.7 ? 'high' : d.confidence >= 0.5 ? 'medium' : 'low';

        // Indicators
        const indicators = d.indicators ? 
          Object.entries(d.indicators)
            .map(([key, val]) => `<span class="indicator-chip">${key.toUpperCase()}: ${typeof val === 'number' ? val.toFixed(1) : val}</span>`)
            .join('') 
          : '<span style="color:var(--text-muted)">--</span>';

        // Reasoning
        const reasoning = d.reasoning || 'No reasoning provided';

        const decisionTime = d.decision_time_display || 'N/A';
        const decisionTimeClass = d.decision_time_ms > 1000 ? 'slow' : d.decision_time_ms > 500 ? 'medium' : 'fast';

        const outcome = d.outcome && d.outcome !== 'PENDING'
          ? `<span class="outcome-badge ${d.outcome.toLowerCase()}">${d.outcome}</span>`
          : '<span style="color:var(--text-muted)">Pending</span>';

        return `
          <tr data-decision="${d.decision}" data-symbol="${d.symbol}">
            <td style="font-size:11px;color:var(--text-secondary)">${timestamp}</td>
            <td><span class="trade-sym" style="font-size:13px">${d.symbol}</span></td>
            <td><span class="decision-badge ${decisionClass}">${decisionDisplay}</span></td>
            <td><span class="score-badge ${confidenceClass}">${confidence}</span></td>
            <td style="max-width:200px">${indicators}</td>
            <td><div class="reasoning-text">${reasoning}</div></td>
            <td><span class="time-badge ${decisionTimeClass}">${decisionTime}</span></td>
            <td>${outcome}</td>
          </tr>
        `;
      }).join("");

    } catch (e) { 
      console.warn("loadDecisionHistory:", e.message);
      const tbody = document.getElementById("decisionHistoryBody");
      if (tbody) {
        // Generate mock data for demonstration
        const mockDecisions = generateMockDecisions();
        const badge = document.getElementById("decisionHistoryBadge");
        if (badge) badge.textContent = `${mockDecisions.length} DECISIONS (DEMO)`;
        
        tbody.innerHTML = mockDecisions.map(d => {
          const timestamp = new Date(d.timestamp).toLocaleString();
          const decisionClass = d.decision === 'EXECUTED' ? 'executed' 
            : d.decision === 'SKIPPED' ? 'skipped' 
            : d.decision === 'REJECTED' ? 'rejected' 
            : 'pending';
          
          const scoreClass = d.signal_score >= 7 ? 'high' 
            : d.signal_score >= 5 ? 'medium' 
            : 'low';

          const indicators = (d.indicators || []).map(ind => 
            `<span class="indicator-chip">${ind}</span>`
          ).join('');

          const outcome = d.outcome 
            ? `<span class="pnl ${d.outcome.pnl >= 0 ? 'pos' : 'neg'}">${d.outcome.pnl >= 0 ? '+' : ''}${_acctCurrency}${Math.abs(d.outcome.pnl).toFixed(2)}</span>`
            : '<span style="color:var(--text-muted)">Pending</span>';

          return `
            <tr data-decision="${d.decision}" data-symbol="${d.symbol}">
              <td style="font-size:11px;color:var(--text-secondary)">${timestamp}</td>
              <td><span class="trade-sym" style="font-size:13px">${d.symbol}</span></td>
              <td><span class="decision-badge ${decisionClass}">${d.decision}</span></td>
              <td><span class="agent-chip">${d.agent_icon || '🤖'} ${d.agent || 'Orchestrator'}</span></td>
              <td><span class="score-badge ${scoreClass}">${d.signal_score ? d.signal_score.toFixed(1) : '--'}</span></td>
              <td style="max-width:200px">${indicators || '<span style="color:var(--text-muted)">--</span>'}</td>
              <td><div class="reasoning-text">${d.reasoning || 'No reasoning provided'}</div></td>
              <td>${outcome}</td>
            </tr>
          `;
        }).join("");
      }
    }
  }

  function generateMockDecisions() {
    const symbols = ['XAUUSD', 'BTCUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'ETHUSD'];
    const agents = [
      { name: 'Market Analyst', icon: '📊' },
      { name: 'Sentiment Agent', icon: '📰' },
      { name: 'Trend Detector', icon: '📈' },
      { name: 'Risk Manager', icon: '🛡️' },
      { name: 'Orchestrator', icon: '🔮' }
    ];
    const decisions = ['EXECUTED', 'SKIPPED', 'REJECTED', 'EXECUTED'];
    const indicators = [
      ['RSI: 68', 'MACD: Bullish', 'EMA Cross'],
      ['ADX: 32', 'Bollinger: Upper', 'Volume: High'],
      ['Stoch: 45', 'ATR: 0.8', 'Support Break'],
      ['RSI: 28', 'MACD: Bearish', 'Trend: Down'],
      ['EMA: Aligned', 'Volume: Low', 'Range Bound']
    ];
    const reasonings = [
      'Strong bullish momentum with RSI confirmation and high volume',
      'Trend reversal signal detected but volume too low for entry',
      'Risk/reward ratio below threshold (1.2:1), position rejected',
      'Perfect setup: trend alignment, sentiment positive, low volatility',
      'Economic calendar shows high-impact event in 15 minutes, skipping',
      'Max open trades limit reached, waiting for position closure',
      'Bearish divergence on multiple timeframes, strong sell signal',
      'Consolidation phase detected, waiting for breakout confirmation'
    ];

    const now = Date.now();
    return Array.from({ length: 15 }, (_, i) => {
      const agent = agents[Math.floor(Math.random() * agents.length)];
      const decision = decisions[Math.floor(Math.random() * decisions.length)];
      const score = decision === 'EXECUTED' ? 7 + Math.random() * 2.5 
        : decision === 'SKIPPED' ? 5 + Math.random() * 2 
        : 3 + Math.random() * 2;
      
      return {
        timestamp: new Date(now - i * 15 * 60 * 1000).toISOString(),
        symbol: symbols[Math.floor(Math.random() * symbols.length)],
        decision: decision,
        agent: agent.name,
        agent_icon: agent.icon,
        signal_score: score,
        indicators: indicators[Math.floor(Math.random() * indicators.length)],
        reasoning: reasonings[Math.floor(Math.random() * reasonings.length)],
        outcome: decision === 'EXECUTED' ? { pnl: (Math.random() - 0.4) * 150 } : null
      };
    });
  }

  function generateMockApexHealth() {
    // Generate 7 days of latency trend data
    const now = Date.now();
    const latencyTrend = Array.from({ length: 7 }, (_, i) => {
      const baseLatency = 150 + Math.random() * 50;
      return {
        timestamp: new Date(now - (6 - i) * 24 * 60 * 60 * 1000).toISOString(),
        avg_latency: baseLatency,
        p95_latency: baseLatency * 1.5 + Math.random() * 30
      };
    });

    // Simulate performance metrics
    const totalCalls = 450 + Math.floor(Math.random() * 150);
    const goCount = Math.floor(totalCalls * 0.35);
    const nogoCount = totalCalls - goCount;
    const goWins = Math.floor(goCount * (0.62 + Math.random() * 0.15));
    
    return {
      status: 'online',
      avg_latency: 165 + Math.random() * 40,
      calls_24h: totalCalls,
      success_rate: 0.95 + Math.random() * 0.04,
      go_count: goCount,
      nogo_count: nogoCount,
      go_winrate: goWins / goCount,
      avg_confidence: 0.72 + Math.random() * 0.15,
      p50_latency: 145 + Math.random() * 30,
      p95_latency: 280 + Math.random() * 50,
      timeouts: Math.floor(Math.random() * 3),
      errors: Math.floor(Math.random() * 2),
      model_name: 'apex-trader',
      last_trained: new Date(now - 5 * 24 * 60 * 60 * 1000).toISOString(),
      training_samples: 1247,
      needs_retrain: Math.random() > 0.8, // 20% chance
      retrain_reason: 'GO win rate dropped below 65% threshold over last 48 hours',
      latency_trend: latencyTrend
    };
  }

  // ── Live log injection ─────────────────────────────

  function injectLogLine(msg) {
    const container = document.getElementById("logContainer");
    if (!container) return;
    const level = (msg.level || "INFO").toUpperCase();
    // Respect active filter set by setLogFilter()
    const activeFilter = (typeof _logFilter !== "undefined") ? _logFilter : "ALL";
    const visible = activeFilter === "ALL" || level.startsWith(activeFilter);
    const div = document.createElement("div");
    div.className = "log-entry log-line";
    div.dataset.level = level;
    if (!visible) div.style.display = "none";
    div.innerHTML = `
      <span class="log-time">${msg.time}</span>
      <span class="log-level ${msg.level}">${msg.level}</span>
      <span class="log-msg">${msg.msg}</span>`;
    container.insertBefore(div, container.firstChild);
    while (container.children.length > 500)
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
    // Status + open trades: every 15s (was 10s — reduces redundant DOM rebuilds)
    setInterval(() => { loadStatus(); loadOpenTrades(); }, 15_000);
    // News + calendar: every 90s (data changes slowly)
    setInterval(() => { loadNews(); loadCalendar(); }, 90_000);
    // Analytics + history: every 120s (heavy DB queries — no need to refresh constantly)
    setInterval(() => { loadAnalytics(); loadTradeHistory(); }, 120_000);
  }

  // ── Init ───────────────────────────────────────────

  function init() {
    connectWS();
    // Note: log handler is registered by the dashboard HTML via APEX.onLog(addLogLine)
    // so it can use the richer version that includes agent tagging and sentiment parsing.
    // injectLogLine here is kept as fallback if no external handler is registered.
    if (_logHandlers.length === 0) onLog(injectLogLine);
    onState(msg => {
      const el = document.querySelector("[data-kpi='open_trades']");
      if (el && msg.open_trades !== undefined) el.textContent = msg.open_trades;
    });
    startAutoRefresh();
    loadAnalytics();
    loadTradeHistory();
    loadCalendar();
    loadConfig();
    console.log("[APEX] Dashboard ready → backend:", BASE);
  }

  // ── Helpers ────────────────────────────────────────

  function _fmt(v) {
    const n = parseFloat(v);
    if (isNaN(n)) return "—";
    return n > 1000
      ? n.toLocaleString(undefined, { maximumFractionDigits: 2 })
      : n.toFixed(5);
  }

  function _duration(iso) {
    if (!iso) return "—";
    const ms = Date.now() - new Date(iso).getTime();
    return `${Math.floor(ms / 3_600_000)}h ${Math.floor((ms % 3_600_000) / 60_000)}m`;
  }

  function _impactDots(impact) {
    const n = { HIGH: 3, MEDIUM: 2, LOW: 1 }[impact] || 1;
    return [1, 2, 3].map(i =>
      `<div class="impact-dot ${i <= n ? "filled high" : "empty"}"></div>`
    ).join("");
  }

  return {
    init, api, onLog, onState,
    loadStatus, loadOpenTrades, loadAnalytics,
    loadNews, loadCalendar, loadConfig, loadTradeHistory, loadDecisionHistory,
    startBot, stopBot, restartBot, saveConfig,
    generateMockApexHealth,
  };
})();

if (document.readyState === "loading")
  document.addEventListener("DOMContentLoaded", APEX.init);
else
  APEX.init();
