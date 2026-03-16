export interface Symbol {
  symbol: string;
  name: string;
  asset_class: string;
}

export interface OHLCV {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface Indicators {
  symbol: string;
  timestamp: string;
  rsi: number;
  adx: number;
  atr: number;
  atr_pct: number;
  ema_20: number;
  ema_50: number;
  ema_200: number;
  macd: number;
  macd_signal: number;
  bb_upper: number;
  bb_lower: number;
  volume_ratio: number;
}

export interface OrderBookLevel {
  price: number;
  volume: number;
  num_orders: number;
}

export interface OrderBook {
  symbol: string;
  timestamp: string;
  bids: OrderBookLevel[];
  asks: OrderBookLevel[];
  bid_volume: number;
  ask_volume: number;
  imbalance: number;
}

export interface PerformanceMetrics {
  total_return: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  max_drawdown: number;
  win_rate: number;
  total_trades: number;
  wins: number;
  losses: number;
  avg_pnl: number;
  profit_factor: number;
  timestamp: string;
}

export interface EquityCurvePoint {
  timestamp: string;
  equity: number;
  pnl: number;
}

export interface Trade {
  entry_id: string;
  timestamp: string;
  symbol: string;
  direction: string;
  entry_price: number;
  exit_price: number;
  pnl: number;
  holding_time_seconds: number;
  exit_reason: string;
}

export interface Decision {
  entry_id: string;
  timestamp: string;
  decision_type: string;
  symbol: string;
  direction: string;
  decision: string;
  confidence: number;
  signal_score: number;
  reasoning: string;
  decision_maker: string;
  pnl?: number;
}

export interface ModelMetadata {
  model_id: string;
  model_name: string;
  model_type: string;
  version: number;
  created_at: string;
  deployment_status: string;
  deployment_environment?: string;
  train_metrics: Record<string, number>;
  validation_metrics: Record<string, number>;
  test_metrics: Record<string, number>;
}

export interface Alert {
  type: string;
  alert_type: string;
  message: string;
  severity: 'info' | 'warning' | 'error' | 'critical';
  timestamp: string;
}

export interface MarketRegime {
  regime: 'trending' | 'ranging' | 'volatile' | 'calm';
  confidence: number;
}
