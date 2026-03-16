/**
 * APEX Health & MLOps Interactive Enhancements
 * Adds real-time updates, interactive charts, and better UX
 */

// ═══════════════════════════════════════════════════════
//  AUTO-REFRESH MANAGER
// ═══════════════════════════════════════════════════════
class AutoRefreshManager {
  constructor(callback, defaultInterval = 10000) {
    this.callback = callback;
    this.interval = defaultInterval;
    this.timer = null;
    this.enabled = false;
    this.lastUpdate = null;
  }

  start() {
    if (this.enabled) return;
    this.enabled = true;
    this.refresh();
    this.timer = setInterval(() => this.refresh(), this.interval);
    console.log(`[AutoRefresh] Started (${this.interval}ms)`);
  }

  stop() {
    if (!this.enabled) return;
    this.enabled = false;
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
    console.log('[AutoRefresh] Stopped');
  }

  setInterval(interval) {
    this.interval = interval;
    if (this.enabled) {
      this.stop();
      this.start();
    }
  }

  async refresh() {
    try {
      this.lastUpdate = new Date();
      await this.callback();
      this.updateTimestamp();
    } catch (e) {
      console.error('[AutoRefresh] Error:', e);
    }
  }

  updateTimestamp() {
    const el = document.getElementById('apex-last-update');
    if (el && this.lastUpdate) {
      const time = this.lastUpdate.toLocaleTimeString();
      el.textContent = `Last updated: ${time}`;
    }
  }
}

// ═══════════════════════════════════════════════════════
//  LLM TIER BREAKDOWN CHART
// ═══════════════════════════════════════════════════════
class LLMTierChart {
  constructor(canvasId) {
    this.canvasId = canvasId;
    this.chart = null;
  }

  create(data) {
    const ctx = document.getElementById(this.canvasId);
    if (!ctx) return;

    if (this.chart) {
      this.chart.destroy();
    }

    this.chart = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels: data.labels,
        datasets: [{
          data: data.values,
          backgroundColor: [
            'rgba(0, 230, 118, 0.8)',   // Ollama - green
            'rgba(0, 180, 255, 0.8)',   // Groq - blue
            'rgba(157, 78, 221, 0.8)',  // DeepSeek - purple
            'rgba(245, 166, 35, 0.8)'   // Claude - amber
          ],
          borderColor: '#0a0f16',
          borderWidth: 2
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: 'right',
            labels: {
              color: '#e8edf5',
              font: { family: 'Rajdhani', size: 12 },
              padding: 15
            }
          },
          tooltip: {
            backgroundColor: '#0e1520',
            titleColor: '#f5a623',
            bodyColor: '#e8edf5',
            borderColor: '#243040',
            borderWidth: 1,
            padding: 12,
            displayColors: true,
            callbacks: {
              label: function(context) {
                const label = context.label || '';
                const value = context.parsed || 0;
                const total = context.dataset.data.reduce((a, b) => a + b, 0);
                const percentage = ((value / total) * 100).toFixed(1);
                return `${label}: ${value} calls (${percentage}%)`;
              }
            }
          }
        }
      }
    });
  }

  update(data) {
    if (!this.chart) {
      this.create(data);
      return;
    }

    this.chart.data.labels = data.labels;
    this.chart.data.datasets[0].data = data.values;
    this.chart.update('none'); // No animation for updates
  }
}

// ═══════════════════════════════════════════════════════
//  LATENCY COMPARISON CHART
// ═══════════════════════════════════════════════════════
class LatencyComparisonChart {
  constructor(canvasId) {
    this.canvasId = canvasId;
    this.chart = null;
  }

  create(data) {
    const ctx = document.getElementById(this.canvasId);
    if (!ctx) return;

    if (this.chart) {
      this.chart.destroy();
    }

    this.chart = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: data.labels,
        datasets: [{
          label: 'Avg Latency (ms)',
          data: data.latencies,
          backgroundColor: [
            'rgba(0, 230, 118, 0.6)',
            'rgba(0, 180, 255, 0.6)',
            'rgba(157, 78, 221, 0.6)',
            'rgba(245, 166, 35, 0.6)'
          ],
          borderColor: [
            'rgba(0, 230, 118, 1)',
            'rgba(0, 180, 255, 1)',
            'rgba(157, 78, 221, 1)',
            'rgba(245, 166, 35, 1)'
          ],
          borderWidth: 2
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          y: {
            beginAtZero: true,
            grid: { color: '#1a2535' },
            ticks: { color: '#6b7a8d', font: { family: 'Share Tech Mono', size: 10 } }
          },
          x: {
            grid: { display: false },
            ticks: { color: '#e8edf5', font: { family: 'Rajdhani', size: 12 } }
          }
        },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: '#0e1520',
            titleColor: '#f5a623',
            bodyColor: '#e8edf5',
            borderColor: '#243040',
            borderWidth: 1,
            padding: 12,
            callbacks: {
              label: function(context) {
                return `Latency: ${context.parsed.y}ms`;
              }
            }
          }
        }
      }
    });
  }

  update(data) {
    if (!this.chart) {
      this.create(data);
      return;
    }

    this.chart.data.labels = data.labels;
    this.chart.data.datasets[0].data = data.latencies;
    this.chart.update('none');
  }
}

// ═══════════════════════════════════════════════════════
//  ALERT MANAGER
// ═══════════════════════════════════════════════════════
class AlertManager {
  constructor() {
    this.alerts = [];
    this.maxAlerts = 50;
  }

  addAlert(type, title, message) {
    const alert = {
      id: Date.now(),
      type, // 'warning', 'error', 'info', 'success'
      title,
      message,
      timestamp: new Date()
    };

    this.alerts.unshift(alert);
    if (this.alerts.length > this.maxAlerts) {
      this.alerts = this.alerts.slice(0, this.maxAlerts);
    }

    this.showToast(alert);
    this.updateAlertPanel();
  }

  showToast(alert) {
    const icons = {
      warning: '⚠️',
      error: '❌',
      info: 'ℹ️',
      success: '✅'
    };

    const colors = {
      warning: '#f5a623',
      error: '#ff3d5a',
      info: '#00b4ff',
      success: '#00e676'
    };

    // Use existing toast function if available
    if (typeof toast === 'function') {
      toast(alert.title, alert.type, alert.message);
    } else {
      console.log(`[Alert] ${icons[alert.type]} ${alert.title}: ${alert.message}`);
    }
  }

  updateAlertPanel() {
    const panel = document.getElementById('apex-alert-history');
    if (!panel) return;

    if (this.alerts.length === 0) {
      panel.innerHTML = '<div style="text-align:center;color:var(--text-muted);padding:20px">No alerts</div>';
      return;
    }

    const html = this.alerts.map(alert => {
      const icons = { warning: '⚠️', error: '❌', info: 'ℹ️', success: '✅' };
      const colors = { warning: 'var(--accent-amber)', error: 'var(--accent-red)', info: 'var(--accent-blue)', success: 'var(--accent-green)' };
      
      return `
        <div style="padding:10px;background:var(--bg-deep);border-left:3px solid ${colors[alert.type]};margin-bottom:8px;border-radius:4px">
          <div style="display:flex;justify-content:space-between;align-items:start;margin-bottom:4px">
            <span style="font-size:12px;font-weight:600;color:${colors[alert.type]}">${icons[alert.type]} ${alert.title}</span>
            <span style="font-size:10px;color:var(--text-muted);font-family:'Share Tech Mono',monospace">${alert.timestamp.toLocaleTimeString()}</span>
          </div>
          <div style="font-size:11px;color:var(--text-secondary)">${alert.message}</div>
        </div>
      `;
    }).join('');

    panel.innerHTML = html;
  }

  clearAlerts() {
    this.alerts = [];
    this.updateAlertPanel();
  }

  getAlerts() {
    return this.alerts;
  }
}

// ═══════════════════════════════════════════════════════
//  APEX HEALTH MONITOR
// ═══════════════════════════════════════════════════════
class ApexHealthMonitor {
  constructor() {
    this.autoRefresh = new AutoRefreshManager(() => this.refresh(), 10000);
    this.tierChart = new LLMTierChart('apex-tier-breakdown-chart');
    this.latencyChart = new LatencyComparisonChart('apex-tier-latency-chart');
    this.alertManager = new AlertManager();
    this.previousHealth = null;
  }

  async init() {
    console.log('[ApexHealthMonitor] Initializing...');
    await this.refresh();
    this.setupEventListeners();
  }

  setupEventListeners() {
    // Auto-refresh toggle
    const toggle = document.getElementById('apex-auto-refresh-toggle');
    if (toggle) {
      toggle.addEventListener('change', (e) => {
        if (e.target.checked) {
          this.autoRefresh.start();
        } else {
          this.autoRefresh.stop();
        }
      });
    }

    // Refresh interval selector
    const intervalSelect = document.getElementById('apex-refresh-interval');
    if (intervalSelect) {
      intervalSelect.addEventListener('change', (e) => {
        const interval = parseInt(e.target.value) * 1000;
        this.autoRefresh.setInterval(interval);
      });
    }

    // Manual refresh button
    const refreshBtn = document.getElementById('apex-manual-refresh');
    if (refreshBtn) {
      refreshBtn.addEventListener('click', () => this.refresh());
    }

    // Test tiers button
    const testBtn = document.getElementById('apex-test-tiers');
    if (testBtn) {
      testBtn.addEventListener('click', () => this.testTiers());
    }

    // Restart Ollama button
    const restartBtn = document.getElementById('apex-restart-ollama');
    if (restartBtn) {
      restartBtn.addEventListener('click', () => this.restartOllama());
    }
  }

  async refresh() {
    try {
      // Fetch health data from correct endpoint
      const health = await fetch('/api/ai/apex-health').then(r => r.json());
      
      // Update UI
      this.updateHealthUI(health);
      
      // Check for alerts
      this.checkAlerts(health);
      
      // Update charts
      await this.updateCharts(health);
      
      this.previousHealth = health;
    } catch (e) {
      console.error('[ApexHealthMonitor] Refresh error:', e);
      this.alertManager.addAlert('error', 'Health Check Failed', e.message);
    }
  }

  updateHealthUI(health) {
    // Status
    const statusEl = document.getElementById('apex-status-kpi');
    if (statusEl) {
      const isOnline = health.status === 'online';
      statusEl.innerHTML = isOnline ? '🟢 ONLINE' : '🔴 OFFLINE';
      statusEl.style.color = isOnline ? 'var(--accent-green)' : 'var(--accent-red)';
    }

    // Latency with color coding
    const latencyEl = document.getElementById('apex-latency-kpi');
    if (latencyEl && health.avg_latency_ms) {
      const latency = health.avg_latency_ms;
      latencyEl.textContent = `${latency}ms`;
      
      if (latency < 1000) {
        latencyEl.style.color = 'var(--accent-green)';
      } else if (latency < 3000) {
        latencyEl.style.color = 'var(--accent-amber)';
      } else {
        latencyEl.style.color = 'var(--accent-red)';
      }
    }

    // Other metrics
    this.updateElement('apex-calls-24h-kpi', health.total_calls_24h);
    this.updateElement('apex-success-rate-kpi', health.success_rate ? `${health.success_rate}%` : '--');
    this.updateElement('apex-go-winrate-kpi', health.go_win_rate ? `${health.go_win_rate}%` : '--');
  }

  updateElement(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value || '--';
  }

  checkAlerts(health) {
    if (!this.previousHealth) return;

    // Ollama went offline
    if (this.previousHealth.status === 'online' && health.status === 'offline') {
      this.alertManager.addAlert('error', 'Ollama Offline', 'Primary LLM tier is no longer responding');
    }

    // Ollama came back online
    if (this.previousHealth.status === 'offline' && health.status === 'online') {
      this.alertManager.addAlert('success', 'Ollama Online', 'Primary LLM tier is now responding');
    }

    // High latency
    if (health.avg_latency_ms > 3000 && this.previousHealth.avg_latency_ms <= 3000) {
      this.alertManager.addAlert('warning', 'High Latency Detected', `Average latency is ${health.avg_latency_ms}ms (threshold: 3000ms)`);
    }

    // Low success rate
    if (health.success_rate < 90 && this.previousHealth.success_rate >= 90) {
      this.alertManager.addAlert('warning', 'Low Success Rate', `Success rate dropped to ${health.success_rate}% (threshold: 90%)`);
    }

    // Retrain recommended
    if (health.retrain_recommended && !this.previousHealth.retrain_recommended) {
      this.alertManager.addAlert('warning', 'Retrain Recommended', health.retrain_reason || 'Model performance degraded');
    }
  }

  async updateCharts(health) {
    // Fetch tier breakdown
    try {
      const tierData = await fetch('/api/apex/health/tier-breakdown').then(r => r.json());
      
      if (tierData.tiers) {
        // Update tier usage chart
        this.tierChart.update({
          labels: tierData.tiers.map(t => t.name),
          values: tierData.tiers.map(t => t.calls)
        });

        // Update latency comparison chart
        this.latencyChart.update({
          labels: tierData.tiers.map(t => t.name),
          latencies: tierData.tiers.map(t => t.avg_latency_ms)
        });
      }
    } catch (e) {
      console.error('[ApexHealthMonitor] Chart update error:', e);
    }
  }

  async testTiers() {
    const btn = document.getElementById('apex-test-tiers');
    if (btn) {
      btn.disabled = true;
      btn.textContent = '⏳ Testing...';
    }

    try {
      const result = await fetch('/api/apex/test-tiers', { method: 'POST' }).then(r => r.json());
      
      if (result.success) {
        this.alertManager.addAlert('success', 'Tier Test Complete', `Tested ${result.tiers_tested} tiers - ${result.tiers_passed} passed`);
      } else {
        this.alertManager.addAlert('error', 'Tier Test Failed', result.message);
      }
    } catch (e) {
      this.alertManager.addAlert('error', 'Tier Test Error', e.message);
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = '🧪 Test LLM Tiers';
      }
    }
  }

  async restartOllama() {
    const btn = document.getElementById('apex-restart-ollama');
    if (btn) {
      btn.disabled = true;
      btn.textContent = '⏳ Restarting...';
    }

    try {
      const result = await fetch('/api/apex/restart-ollama', { method: 'POST' }).then(r => r.json());
      
      if (result.success) {
        this.alertManager.addAlert('success', 'Ollama Restarted', 'Service restarted successfully');
        setTimeout(() => this.refresh(), 3000);
      } else {
        this.alertManager.addAlert('error', 'Restart Failed', result.message);
      }
    } catch (e) {
      this.alertManager.addAlert('error', 'Restart Error', e.message);
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = '🔄 Restart Ollama';
      }
    }
  }
}

// ═══════════════════════════════════════════════════════
//  GLOBAL INSTANCE
// ═══════════════════════════════════════════════════════
let apexHealthMonitor = null;

// Initialize when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    apexHealthMonitor = new ApexHealthMonitor();
  });
} else {
  apexHealthMonitor = new ApexHealthMonitor();
}

// Export for use in dashboard
window.ApexHealthMonitor = ApexHealthMonitor;
window.apexHealthMonitor = apexHealthMonitor;
