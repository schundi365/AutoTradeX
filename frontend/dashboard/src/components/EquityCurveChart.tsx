import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { EquityCurvePoint } from '../types';

interface EquityCurveChartProps {
  data: EquityCurvePoint[];
}

export default function EquityCurveChart({ data }: EquityCurveChartProps) {
  // Calculate drawdown
  const dataWithDrawdown = data.map((point, index) => {
    const peak = Math.max(...data.slice(0, index + 1).map((p) => p.equity));
    const drawdown = ((point.equity - peak) / peak) * 100;
    return {
      ...point,
      drawdown,
      timestamp: new Date(point.timestamp).toLocaleString(),
    };
  });

  return (
    <div className="bg-white rounded-lg shadow">
      <div className="px-6 py-4 border-b border-gray-200">
        <h3 className="text-lg font-medium text-gray-900">Equity Curve</h3>
      </div>
      <div className="p-6">
        <ResponsiveContainer width="100%" height={400}>
          <LineChart data={dataWithDrawdown}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="timestamp" tick={{ fontSize: 12 }} />
            <YAxis yAxisId="left" tick={{ fontSize: 12 }} />
            <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 12 }} />
            <Tooltip />
            <Legend />
            <Line
              yAxisId="left"
              type="monotone"
              dataKey="equity"
              stroke="#0ea5e9"
              strokeWidth={2}
              dot={false}
              name="Equity"
            />
            <Line
              yAxisId="right"
              type="monotone"
              dataKey="drawdown"
              stroke="#ef4444"
              strokeWidth={2}
              dot={false}
              name="Drawdown %"
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
