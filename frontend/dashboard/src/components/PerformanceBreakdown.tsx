import { Trade } from '../types';

interface PerformanceBreakdownProps {
  trades: Trade[];
}

export default function PerformanceBreakdown({ trades }: PerformanceBreakdownProps) {
  // Group by symbol
  const bySymbol = trades.reduce((acc, trade) => {
    if (!acc[trade.symbol]) {
      acc[trade.symbol] = { pnl: 0, count: 0 };
    }
    acc[trade.symbol].pnl += trade.pnl;
    acc[trade.symbol].count += 1;
    return acc;
  }, {} as Record<string, { pnl: number; count: number }>);

  const symbolData = Object.entries(bySymbol).map(([symbol, data]) => ({
    symbol,
    pnl: data.pnl,
    count: data.count,
    avgPnl: data.pnl / data.count,
  }));

  return (
    <div className="bg-white rounded-lg shadow">
      <div className="px-6 py-4 border-b border-gray-200">
        <h3 className="text-lg font-medium text-gray-900">Performance Breakdown</h3>
      </div>
      <div className="p-6">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead>
              <tr>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                  Symbol
                </th>
                <th className="px-4 py-2 text-right text-xs font-medium text-gray-500 uppercase">
                  Trades
                </th>
                <th className="px-4 py-2 text-right text-xs font-medium text-gray-500 uppercase">
                  Total P&L
                </th>
                <th className="px-4 py-2 text-right text-xs font-medium text-gray-500 uppercase">
                  Avg P&L
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {symbolData.map((row) => (
                <tr key={row.symbol}>
                  <td className="px-4 py-2 text-sm font-medium text-gray-900">{row.symbol}</td>
                  <td className="px-4 py-2 text-sm text-right text-gray-500">{row.count}</td>
                  <td
                    className={`px-4 py-2 text-sm text-right font-medium ${
                      row.pnl >= 0 ? 'text-green-600' : 'text-red-600'
                    }`}
                  >
                    ${row.pnl.toFixed(2)}
                  </td>
                  <td
                    className={`px-4 py-2 text-sm text-right ${
                      row.avgPnl >= 0 ? 'text-green-600' : 'text-red-600'
                    }`}
                  >
                    ${row.avgPnl.toFixed(2)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
