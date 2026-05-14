export interface OHLCVBar {
  time: number
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export interface Ticker {
  symbol: string
  last: number
  bid: number
  ask: number
  change_pct: number
  volume: number
}

export interface ExchangeAccount {
  id: number
  exchange: string
  label: string
  api_key_masked: string
  is_paper: boolean
  is_active: boolean
  created_at: string
}

export interface RiskConfig {
  stop_loss_pct: number
  take_profit_pct: number
  position_size_pct: number
  trailing_stop?: boolean
  trailing_pct?: number
}

export interface IndicatorCondition {
  id: string
  indicator: string
  params: Record<string, number>
  operator: '<' | '>' | '<=' | '>=' | '==' | 'cross_above' | 'cross_below'
  value?: number
}

export interface StrategyConfig {
  symbol: string
  timeframe: string
  exchange?: string
  entry_conditions: IndicatorCondition[]
  exit_conditions: IndicatorCondition[]
  risk: RiskConfig
}

export interface Strategy {
  id: number
  name: string
  description?: string
  config: StrategyConfig
  is_active: boolean
  is_paper: boolean
  total_trades: number
  win_rate: number
  total_pnl_pct: number
  max_drawdown_pct: number
  sharpe_ratio: number
}

export interface Trade {
  id: number
  strategy_id: number
  symbol: string
  direction: string
  entry_price: number
  exit_price: number
  amount: number
  pnl: number
  pnl_pct: number
  exit_reason: string
  is_paper: boolean
  entry_at: string
  exit_at: string
}

export interface BacktestRequest {
  strategy_config: StrategyConfig
  exchange?: string
  initial_capital?: number
  fee_rate?: number
  walk_forward?: boolean
  n_splits?: number
}

export interface BacktestResult {
  total_trades: number
  win_rate: number
  total_pnl_pct: number
  max_drawdown_pct: number
  sharpe_ratio: number
  profit_factor: number
  avg_trade_pnl_pct: number
  max_consecutive_losses: number
  equity_curve: number[]
  timestamps: string[]
  trades: BacktestTrade[]
  walk_forward_results?: WalkForwardResult[]
  indicator_snapshot?: { label: string; current_value: number | string; operator: string; threshold: number | null }[]
}

export interface BacktestTrade {
  entry_at: string
  exit_at: string
  entry_price: number
  exit_price: number
  pnl: number
  pnl_pct: number
  exit_reason: string
}

export interface WalkForwardResult {
  total_trades: number
  win_rate: number
  total_pnl_pct: number
  max_drawdown_pct: number
  sharpe_ratio: number
}

export interface BotPosition {
  symbol: string
  direction: string
  entry_price: number
  amount: number
  stop_loss_price?: number
  take_profit_price?: number
  unrealized_pnl: number
  unrealized_pnl_pct: number
  entry_at: string
}

export interface BotState {
  strategy_id: number
  name: string
  symbol: string
  timeframe: string
  is_paper: boolean
  position: BotPosition | null
}

export interface PortfolioAccount {
  account_id: number
  label: string
  krw_free: number
  coins_krw: number
  total_krw: number
}

export interface Portfolio {
  has_real_account: boolean
  total_krw: number
  accounts: PortfolioAccount[]
}

export interface PositionEntry {
  price: number
  amount: number
  at: string
  type: 'initial' | 'avg_down' | 'add' | 'pyramid'
}

export interface AutoBotPosition {
  symbol: string
  entries: PositionEntry[]
  avg_price: number
  total_amount: number
  stop_loss_price: number
  take_profit_price: number
  current_price: number
  unrealized_pnl_pct: number
  unrealized_pnl_krw: number
  total_fee_krw?: number
  entry_at: string
  score: number
  signals: string[]
  strategy_type: string
  strategy_label: string
  position_style: string
  position_style_label: string
  avg_down_count: number
  add_count: number
  pyramid_count: number
}

export interface AutoBotTradeLog {
  symbol: string
  avg_price: number
  exit_price: number
  total_amount: number
  entries: PositionEntry[]
  pnl_pct: number
  pnl_krw: number
  exit_reason: string
  entry_at: string
  exit_at: string
  score: number
  avg_down_count: number
  add_count: number
}

export interface ScanResult {
  symbol: string
  score: number
  rsi: number
  price: number
  signals: string[]
  strategy_type: string
  strategy_label: string
  sl_pct: number | null
  tp_pct: number | null
  mtf_trend?: 'bullish' | 'bearish' | 'neutral'
  mtf_confirmed?: boolean
}

export interface AutoBotSettings {
  exchange_id?: string
  is_paper?: boolean
  trading_style: string
  risk_profile?: string
  scan_interval_min: number
  max_positions: number
  position_size_pct: number
  stop_loss_pct: number
  take_profit_pct: number
  min_score: number
  timeframe: string
  auto_avg_down: boolean
  avg_down_threshold_pct: number
  max_avg_down: number
  auto_add: boolean
  add_threshold_pct: number
  max_add: number
  ai_entry_validation: boolean
  ai_regime_detection: boolean
  ai_loss_analysis: boolean
  ai_exit_assist: boolean
  max_daily_loss_pct: number
  max_portfolio_exposure_pct: number
  // 피라미딩
  pyramid_enabled?: boolean
  pyramid_threshold_pct?: number
  max_pyramid?: number
  // 선물 설정
  market_type?: 'spot' | 'futures'
  leverage?: number
  margin_mode?: 'cross' | 'isolated'
}

export interface FuturesPosition {
  symbol: string
  side: 'long' | 'short'
  entry_price: number
  contracts: number
  leverage: number
  margin_mode: 'cross' | 'isolated'
  initial_margin: number
  liquidation_price: number | null
  stop_loss_price: number
  take_profit_price: number
  current_price: number
  unrealized_pnl_usdt: number
  unrealized_pnl_pct: number
  funding_rate: number
  score: number
  signals: string[]
  strategy_type: string
  strategy_label: string
  entry_at: string
}

export interface AiAnalysisLogEntry {
  at: string
  type: 'regime_change' | 'loss_analysis' | 'entry_blocked' | 'exit_action' | 'surge_override' | 'performance_feedback' | 'opportunistic_entry' | 'scalping_parallel'
  regime?: string
  style?: string
  reason?: string
  changed?: string[]
  symbol?: string
  confidence?: number
  action?: 'close_now' | 'tighten_sl'
  pnl_pct?: number
  issue?: string
  adjusted?: string[]
  volume_ratio?: number
  price_change_pct?: number
  score?: number
}

export interface StylePreset {
  key: string
  label: string
  timeframe: string
  scan_interval_min: number
  stop_loss_pct: number
  take_profit_pct: number
  min_score: number
  position_size_pct: number
  max_positions: number
  auto_avg_down: boolean
  avg_down_threshold_pct: number
  max_avg_down: number
  auto_add: boolean
  add_threshold_pct: number
  max_add: number
}

export interface AutoBotStatus {
  running: boolean
  paused: boolean
  scan_in_progress: boolean
  positions: AutoBotPosition[]
  futures_positions?: FuturesPosition[]
  trade_log: AutoBotTradeLog[]
  scan_results: ScanResult[]
  last_scan_at: string | null
  balance_krw: number
  fee_rate: number
  total_value_krw: number
  unrealized_pnl_krw: number
  unrealized_pnl_pct: number
  realized_pnl_krw: number
  avg_pnl_pct: number
  total_trades: number
  settings: AutoBotSettings
  style_label: string
  started_at: string | null
  ai_available: boolean
  ai_regime: {
    regime: string
    style: string
    min_score_delta: number
    reason: string
  }
  ai_consecutive_losses: number
  ai_analysis_log: AiAnalysisLogEntry[]
  performance: PerformanceStats
  daily_pnl_krw: number
  // 선물 전용
  market_type?: 'spot' | 'futures'
  leverage?: number
  margin_mode?: 'cross' | 'isolated'
}

export interface AutoBotTradeDB {
  id: number
  symbol: string
  avg_price: number
  exit_price: number
  total_amount: number
  entries: PositionEntry[]
  pnl_pct: number
  pnl_krw: number
  exit_reason: string
  strategy_type: string
  strategy_label: string
  score: number
  avg_down_count: number
  add_count: number
  entry_at: string
  exit_at: string
  is_paper: boolean
}

export interface AutoBotTradeStats {
  total: number
  win_trades: number
  loss_trades: number
  win_rate: number
  total_pnl_krw: number
  avg_pnl_pct: number
  best_trade_pct: number
  worst_trade_pct: number
}

export interface PerformanceStats {
  sharpe_ratio: number
  sortino_ratio: number
  calmar_ratio: number
  profit_factor: number
  expectancy_pct: number
  max_drawdown_pct: number
  avg_win_pct: number
  avg_loss_pct: number
  win_rate: number
  best_trade_pct: number
  worst_trade_pct: number
  total_trades: number
}

export interface User {
  id: number
  email: string
  username: string
  is_active: boolean
}
