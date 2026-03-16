import { Indicators } from '../types';

interface TechnicalIndicatorsProps {
  indicators: Indicators | null;
}

export default function TechnicalIndicators({ indicators }: TechnicalIndicatorsProps) {
  if (!indicators) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-medium text-gray-900 mb-4">Technical Indicators</h3>
        <p className="text-sm text-gray-500">Loading indicators...</p>
      </div>
    );
  }

  const getIndicatorColor = (value: number, type: string) => {
    if (type === 'rsi') {
      if (value > 70) return 'text-red-600';
      if (value < 30) return 'text-green-600';
      return 'text-gray-900';
    }
    if (type === 'adx') {
      if (value > 25) return 'text-green-600';
      return 'text-gray-900';
    }
    return 'text-gray-900';
  };

  const indicatorsList = [
    { label: 'RSI', value: indicators.rsi?.toFixed(2), type: 'rsi' },
    { label: 'ADX', value: indicators.adx?.toFixed(2), type: 'adx' },
    { label: 'ATR', value: indicators.atr?.toFixed(2), type: 'atr' },
    { label: 'ATR %', value: `${indicators.atr_pct?.toFixed(2)}%`, type: 'atr_pct' },
    { label: 'EMA 20', value: indicators.ema_20?.toFixed(2), type: 'ema' },
    { label: 'EMA 50', value: indicators.ema_50?.toFixed(2), type: 'ema' },
    { label: 'EMA 200', value: indicators.ema_200?.toFixed(2), type: 'ema' },
    { label: 'MACD', value: indicators.macd?.toFixed(2), type: 'macd' },
    { label: 'MACD Signal', value: indicators.macd_signal?.toFixed(2), type: 'macd' },
    { label: 'BB Upper', value: indicators.bb_upper?.toFixed(2), type: 'bb' },
    { label: 'BB Lower', value: indicators.bb_lower?.toFixed(2), type: 'bb' },
    { label: 'Volume Ratio', value: indicators.volume_ratio?.toFixed(2), type: 'volume' },
  ];

  return (
    <div className="bg-white rounded-lg shadow">
      <div className="px-6 py-4 border-b border-gray-200">
        <h3 className="text-lg font-medium text-gray-900">Technical Indicators</h3>
        <p className="text-xs text-gray-500 mt-1">{indicators.symbol}</p>
      </div>
      <div className="p-6">
        <div className="grid grid-cols-2 gap-4">
          {indicatorsList.map((indicator) => (
            <div key={indicator.label} className="flex justify-between items-center">
              <span className="text-sm text-gray-600">{indicator.label}</span>
              <span
                className={`text-sm font-medium ${getIndicatorColor(
                  parseFloat(indicator.value || '0'),
                  indicator.type
                )}`}
              >
                {indicator.value || '-'}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
