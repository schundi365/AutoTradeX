import { Decision } from '../types';

interface DecisionMakerBreakdownProps {
  decisions: Decision[];
}

export default function DecisionMakerBreakdown({ decisions }: DecisionMakerBreakdownProps) {
  const breakdown = decisions.reduce((acc, decision) => {
    const maker = decision.decision_maker;
    if (!acc[maker]) {
      acc[maker] = { total: 0, go: 0, nogo: 0, wins: 0, losses: 0, totalPnl: 0 };
    }
    acc[maker].total += 1;
    if (decision.decision === 'GO') acc[maker].go += 1;
    if (decision.decision === 'NOGO') acc[maker].nogo += 1;
    if (decision.pnl !== undefined && decision.pnl !== null) {
      if (decision.pnl > 0) acc[maker].wins += 1;
      if (decision.pnl < 0) acc[maker].losses += 1;
      acc[maker].totalPnl += decision.pnl;
    }
    return acc;
  }, {} as Record<string, any>);

  return (
    <div className="bg-white rounded-lg shadow">
      <div className="px-6 py-4 border-b border-gray-200">
        <h3 className="text-lg font-medium text-gray-900">Decision Maker Breakdown</h3>
      </div>
      <div className="p-6">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {Object.entries(breakdown).map(([maker, stats]: [string, any]) => (
            <div key={maker} className="border border-gray-200 rounded-lg p-4">
              <h4 className="text-sm font-medium text-gray-900 mb-3">{maker}</h4>
              <div className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-gray-600">Total Decisions</span>
                  <span className="font-medium">{stats.total}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-600">GO / NOGO</span>
                  <span className="font-medium">
                    {stats.go} / {stats.nogo}
                  </span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-600">Win Rate</span>
                  <span className="font-medium">
                    {stats.wins + stats.losses > 0
                      ? ((stats.wins / (stats.wins + stats.losses)) * 100).toFixed(1)
                      : 0}
                    %
                  </span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-600">Total P&L</span>
                  <span
                    className={`font-medium ${
                      stats.totalPnl >= 0 ? 'text-green-600' : 'text-red-600'
                    }`}
                  >
                    ${stats.totalPnl.toFixed(2)}
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
