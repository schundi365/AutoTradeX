import { Trade } from '../types';

interface RollingPerformanceProps {
  trades: Trade[];
}

export default function RollingPerformance({ trades }: RollingPerformanceProps) {
  const calculateRollingMetrics = (windowDays: number) => {
    const cutoff = new Date(Date.now() - windowDays * 24 * 60 * 60 * 1000);
    const windowTrades = trades.filter((t) => new Date(t.timestamp) >= cutoff);
    
    const totalPnl = windowTrades.reduce((sum, t) => sum + t.pnl, 0);
    const wins = windowTrades.filter((t) => t.pnl > 0).length;
    const winRate = windowTrades.length > 0 ? wins / windowTrades.length : 0;
    
    return {
      trades: windowTrades.length,
      pnl: totalPnl,
      winRate,
    };
  };

  const windows = [
    { label: '1 Day', days: 1 },
    { label: '1 Week', days: 7 },
    { label: '1 Month', days: 30 },
  ];

  return (
    <div className="bg-white rounded-lg shadow">
      <div className="px-6 py-4 border-b border-gray-200">
        <h3 className="text-lg font-medium text-gray-900">Rolling Performance</h3>
      </div>
      <div className="p-6">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {windows.map((window) => {
            const metrics = calculateRollingMetrics(window.days);
            return (
              <div key={window.label} className="border border-gray-200 rounded-lg p-4">
                <h4 className="text-sm font-medium text-gray-500 mb-3">{window.label}</h4>
                <div className="space-y-2">
                  <div className="flex justify-between">
                    <span className="text-sm text-gray-600">Trades</span>
                    <span className="text-sm font-medium text-gray-900">{metrics.trades}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-sm text-gray-600">P&L</span>
                    <span
                      className={`text-sm font-medium ${
                        metrics.pnl >= 0 ? 'text-green-600' : 'text-red-600'
                      }`}
                    >
                      ${metrics.pnl.toFixed(2)}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-sm text-gray-600">Win Rate</span>
                    <span className="text-sm font-medium text-gray-900">
                      {(metrics.winRate * 100).toFixed(1)}%
                    </span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
