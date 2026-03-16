interface MarketRegimeIndicatorProps {
  regime: string;
}

export default function MarketRegimeIndicator({ regime }: MarketRegimeIndicatorProps) {
  const getRegimeColor = (regime: string) => {
    switch (regime.toLowerCase()) {
      case 'trending':
        return 'bg-green-100 text-green-800 border-green-200';
      case 'ranging':
        return 'bg-blue-100 text-blue-800 border-blue-200';
      case 'volatile':
        return 'bg-red-100 text-red-800 border-red-200';
      case 'calm':
        return 'bg-gray-100 text-gray-800 border-gray-200';
      default:
        return 'bg-gray-100 text-gray-800 border-gray-200';
    }
  };

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <h3 className="text-sm font-medium text-gray-500 mb-2">Market Regime</h3>
      <div className="flex items-center space-x-4">
        <div
          className={`px-4 py-2 rounded-lg border-2 ${getRegimeColor(regime)}`}
        >
          <span className="text-lg font-bold uppercase">{regime}</span>
        </div>
        <p className="text-sm text-gray-600">
          Current market conditions indicate a {regime.toLowerCase()} environment
        </p>
      </div>
    </div>
  );
}
