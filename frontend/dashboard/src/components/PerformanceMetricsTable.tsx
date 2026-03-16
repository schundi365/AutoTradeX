import { PerformanceMetrics } from '../types';

interface PerformanceMetricsTableProps {
  metrics: PerformanceMetrics | null;
}

export default function PerformanceMetricsTable({ metrics }: PerformanceMetricsTableProps) {
  if (!metrics) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-medium text-gray-900 mb-4">Performance Metrics</h3>
        <p className="text-sm text-gray-500">Loading metrics...</p>
      </div>
    );
  }

  const metricsList = [
    { label: 'Total Return', value: `${(metrics.total_return * 100).toFixed(2)}%`, positive: metrics.total_return > 0 },
    { label: 'Sharpe Ratio', value: metrics.sharpe_ratio.toFixed(2), positive: metrics.sharpe_ratio > 0 },
    { label: 'Sortino Ratio', value: metrics.sortino_ratio.toFixed(2), positive: metrics.sortino_ratio > 0 },
    { label: 'Max Drawdown', value: `${(metrics.max_drawdown * 100).toFixed(2)}%`, positive: false },
    { label: 'Win Rate', value: `${(metrics.win_rate * 100).toFixed(1)}%`, positive: metrics.win_rate > 0.5 },
    { label: 'Total Trades', value: metrics.total_trades.toString(), positive: null },
    { label: 'Wins', value: metrics.wins.toString(), positive: true },
    { label: 'Losses', value: metrics.losses.toString(), positive: false },
    { label: 'Avg P&L', value: `$${metrics.avg_pnl.toFixed(2)}`, positive: metrics.avg_pnl > 0 },
    { label: 'Profit Factor', value: metrics.profit_factor.toFixed(2), positive: metrics.profit_factor > 1 },
  ];

  return (
    <div className="bg-white rounded-lg shadow">
      <div className="px-6 py-4 border-b border-gray-200">
        <h3 className="text-lg font-medium text-gray-900">Performance Metrics</h3>
      </div>
      <div className="p-6">
        <div className="grid grid-cols-2 md:grid-cols-5 gap-6">
          {metricsList.map((metric) => (
            <div key={metric.label}>
              <p className="text-xs text-gray-500 uppercase tracking-wide">{metric.label}</p>
              <p
                className={`text-2xl font-bold mt-1 ${
                  metric.positive === null
                    ? 'text-gray-900'
                    : metric.positive
                    ? 'text-green-600'
                    : 'text-red-600'
                }`}
              >
                {metric.value}
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
