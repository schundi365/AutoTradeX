import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { Trade } from '../types';

interface TradeDistributionChartsProps {
  trades: Trade[];
}

export default function TradeDistributionCharts({ trades }: TradeDistributionChartsProps) {
  // Calculate P&L distribution
  const pnlBuckets = [-100, -50, -20, -10, 0, 10, 20, 50, 100];
  const pnlDistribution = pnlBuckets.map((bucket, index) => {
    const nextBucket = pnlBuckets[index + 1] || Infinity;
    const count = trades.filter((t) => t.pnl >= bucket && t.pnl < nextBucket).length;
    return {
      range: `${bucket} to ${nextBucket === Infinity ? '+' : nextBucket}`,
      count,
    };
  });

  return (
    <div className="bg-white rounded-lg shadow">
      <div className="px-6 py-4 border-b border-gray-200">
        <h3 className="text-lg font-medium text-gray-900">Trade Distribution</h3>
      </div>
      <div className="p-6">
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={pnlDistribution}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="range" tick={{ fontSize: 12 }} />
            <YAxis tick={{ fontSize: 12 }} />
            <Tooltip />
            <Legend />
            <Bar dataKey="count" fill="#0ea5e9" name="Number of Trades" />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
