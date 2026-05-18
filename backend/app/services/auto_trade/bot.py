"""
자동매매봇 - 시장 스캔 → 자동 종목 선택 → 자동 진입/청산.

포지션 관리:
  - 다중 진입 지원 (entries 리스트로 평단가 추적)
  - 자동 물타기: 평단 대비 N% 하락 시 추가 매수 (최대 2회)
  - 자동 추매: 평단 대비 N% 상승 시 추가 매수 (기본 OFF)
  - 수동 물타기/추매/청산 API 지원
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

KST = timezone(timedelta(hours=9))
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from ..exchange.connector import ExchangeConnector, PaperBroker, BinanceFuturesConnector, FuturesPaperBroker, FUTURES_FEE_RATE
from .scanner import scan_market, scan_futures_market, FUTURES_SYMBOLS, STRATEGY_CONFIGS, STRATEGY_STYLE_CONFIGS, TIMEFRAME_MINUTES, HTF_MAP
from . import ai_analyst
from ..risk.manager import PortfolioRiskManager, calc_performance, calc_futures_position_size, calc_kelly_fraction

logger = logging.getLogger(__name__)

MAX_TRADE_LOG = 50

# ── 매매 스타일 프리셋 ────────────────────────────────────────────────────────
TRADING_STYLE_PRESETS: dict[str, dict] = {
    "scalping": {
        "label": "초단타",
        "timeframe": "5m",
        "scan_interval_min": 1,
        "stop_loss_pct": 1.0,
        "take_profit_pct": 2.0,
        "min_score": 55,
        "position_size_pct": 20.0,
        "max_positions": 5,
        "auto_avg_down": False,
        "avg_down_threshold_pct": 1.0,
        "max_avg_down": 1,
        "auto_add": False,
        "add_threshold_pct": 1.5,
        "max_add": 1,
        # 트레일링 스탑: 1.5% 이익 시 활성화 → 고점 대비 0.8% 하락 시 청산
        "trailing_stop": True,
        "trailing_activate_pct": 1.5,
        "trailing_pct": 0.8,
    },
    "short": {
        "label": "단타",
        "timeframe": "15m",
        "scan_interval_min": 5,
        "stop_loss_pct": 2.5,
        "take_profit_pct": 6.0,
        "min_score": 55,
        "position_size_pct": 25.0,
        "max_positions": 4,
        "auto_avg_down": True,
        "avg_down_threshold_pct": 3.0,
        "max_avg_down": 2,
        "auto_add": False,
        "add_threshold_pct": 3.0,
        "max_add": 1,
        # 트레일링 스탑: 4% 이익 시 활성화 → 고점 대비 2% 하락 시 청산
        "trailing_stop": True,
        "trailing_activate_pct": 4.0,
        "trailing_pct": 2.0,
    },
    "mid": {
        "label": "중장기",
        "timeframe": "4h",
        "scan_interval_min": 15,
        "stop_loss_pct": 6.0,
        "take_profit_pct": 18.0,
        "min_score": 50,
        "position_size_pct": 30.0,
        "max_positions": 3,
        "auto_avg_down": True,
        "avg_down_threshold_pct": 7.0,
        "max_avg_down": 2,
        "auto_add": False,
        "add_threshold_pct": 8.0,
        "max_add": 1,
        # 트레일링 스탑: 10% 이익 시 활성화 → 고점 대비 5% 하락 시 청산
        "trailing_stop": True,
        "trailing_activate_pct": 10.0,
        "trailing_pct": 5.0,
    },
    "long": {
        "label": "장기",
        "timeframe": "1d",
        "scan_interval_min": 60,
        "stop_loss_pct": 12.0,
        "take_profit_pct": 35.0,
        "min_score": 45,
        "position_size_pct": 33.0,
        "max_positions": 3,
        "auto_avg_down": True,
        "avg_down_threshold_pct": 15.0,
        "max_avg_down": 2,
        "auto_add": False,
        "add_threshold_pct": 20.0,
        "max_add": 1,
        # 트레일링 스탑: 20% 이익 시 활성화 → 고점 대비 10% 하락 시 청산
        "trailing_stop": True,
        "trailing_activate_pct": 20.0,
        "trailing_pct": 10.0,
    },
}


# ── 투자 성향 프로파일 ────────────────────────────────────────────────────────
# 스타일 프리셋 기본값에 곱/가산하는 조정치. "balanced"는 변경 없음.
RISK_PROFILE_ADJUSTMENTS: dict[str, dict] = {
    "conservative": {
        "label": "보수적",
        "position_size_pct_mult": 0.6,   # 포지션 크기 60%
        "min_score_delta": 10,            # 진입 기준 +10점 (더 엄격)
        "max_positions_delta": -1,        # 최대 포지션 -1
        "stop_loss_pct_mult": 0.7,        # 손절 더 타이트
        "take_profit_pct_mult": 0.8,      # 익절 더 낮게
        "auto_avg_down": False,
        "auto_add": False,
    },
    "balanced": {
        "label": "균형",
    },
    "aggressive": {
        "label": "공격적",
        "position_size_pct_mult": 1.5,   # 포지션 크기 150%
        "min_score_delta": -10,           # 진입 기준 -10점 (더 완화)
        "max_positions_delta": 2,         # 최대 포지션 +2
        "stop_loss_pct_mult": 1.5,        # 손절 더 넓게 (버티기)
        "take_profit_pct_mult": 1.5,      # 익절 더 높게
        "auto_avg_down": True,
        "auto_add": True,
    },
}


def apply_risk_profile(preset: dict, profile: str) -> dict:
    """스타일 프리셋에 투자 성향 조정을 적용한 복사본 반환"""
    adj = RISK_PROFILE_ADJUSTMENTS.get(profile, {})
    result = dict(preset)
    if "position_size_pct_mult" in adj:
        result["position_size_pct"] = round(preset["position_size_pct"] * adj["position_size_pct_mult"], 1)
    if "min_score_delta" in adj:
        result["min_score"] = int(min(90, max(30, preset["min_score"] + adj["min_score_delta"])))
    if "max_positions_delta" in adj:
        result["max_positions"] = max(1, preset["max_positions"] + adj["max_positions_delta"])
    if "stop_loss_pct_mult" in adj:
        result["stop_loss_pct"] = round(preset["stop_loss_pct"] * adj["stop_loss_pct_mult"], 1)
    if "take_profit_pct_mult" in adj:
        result["take_profit_pct"] = round(preset["take_profit_pct"] * adj["take_profit_pct_mult"], 1)
    if "auto_avg_down" in adj:
        result["auto_avg_down"] = adj["auto_avg_down"]
    if "auto_add" in adj:
        result["auto_add"] = adj["auto_add"]
    return result


# ── 스타일별 선호 전략 순서 ──────────────────────────────────────────────────
# 각 스타일에서 신호 강도가 동일하다면 앞쪽 전략을 우선 진입
STYLE_PREFERRED_STRATEGIES: dict[str, list[str]] = {
    "scalping": ["macd_momentum", "volume_breakout"],
    "short":    ["volume_breakout", "macd_momentum", "oversold_bounce"],
    "mid":      ["oversold_bounce", "golden_cross", "macd_momentum"],
    "long":     ["oversold_bounce", "golden_cross"],
}

# 스타일별 신호 약화 시 SL 보호 임계 (이익 구간에서 SL 상향)
STYLE_SL_PROTECT_PCT: dict[str, float] = {
    "scalping": 0.3,   # 0.3% 위로 SL 올림
    "short":    0.5,
    "mid":      1.0,
    "long":     2.0,
}


class AutoTradeBot:
    def __init__(self):
        self._scheduler = AsyncIOScheduler()
        self._running = False
        self._positions: dict[str, dict] = {}
        self._trade_log: list[dict] = []
        self._scan_results: list[dict] = []
        self._last_scan_at: Optional[str] = None
        self._scan_in_progress = False
        self._paused = False
        self._connector: Optional[ExchangeConnector] = None
        self._broker = PaperBroker(initial_balance=0, fee_rate=0.0005)
        self._broker.balance = {"KRW": 1_000_000}   # start() 시 exchange_id에 맞게 재설정됨
        self._price_task: Optional[asyncio.Task] = None
        self._started_at: Optional[datetime] = None

        # ── 선물 거래 전용 ────────────────────────────────────────────────────
        self._futures_connector: Optional[BinanceFuturesConnector] = None
        self._futures_broker = FuturesPaperBroker(initial_balance=1_000.0)
        self._futures_positions: dict[str, dict] = {}   # 선물 포지션 (롱/숏)
        self._last_funding_check: float = 0.0           # 마지막 펀딩비 체크 시각

        # 전략별 실적 추적 (wins/losses/total_pnl)
        self._strategy_performance: dict[str, dict] = {
            k: {"wins": 0, "losses": 0, "total_pnl": 0.0}
            for k in ["oversold_bounce", "golden_cross", "macd_momentum", "volume_breakout", "standard"]
        }

        # AI 기능 상태
        self._consecutive_losses: int = 0          # 연속 손절 카운터
        self._cooldown_until: float = 0.0          # 연속 손절 쿨다운 종료 시각 (T2)
        self._reentry_blacklist: dict[str, float] = {}  # symbol → 재진입 허용 시각 (T1)
        self._last_regime_at: float = 0.0          # 마지막 국면 감지 시각 (epoch)
        self._last_perf_feedback_at: float = 0.0   # 마지막 성과 피드백 시각 (epoch)
        self._current_regime: dict = {             # 현재 시장 국면
            "regime": "ranging", "style": "short",
            "min_score_delta": 0, "reason": "초기화",
            "strategy_mode": "momentum",
        }
        self._analysis_log: list[dict] = []        # AI 분석 기록 (최대 20건)

        # 포트폴리오 리스크 관리
        self._portfolio_risk = PortfolioRiskManager()
        self._close_cache: dict[str, list[float]] = {}   # symbol → 1h 종가 리스트 (상관관계 체크용)

        # DB 전략 캐시 (Strategy Builder ↔ AutoBot 연동, TODO 9)
        self._db_strategy_cache: list[dict] = []
        self._db_strategy_cache_ts: float = 0.0

        self.settings: dict = {
            "exchange_id": "upbit",         # "upbit" | "binance" | "bybit"
            "trading_style": "short",
            "risk_profile": "balanced",     # "conservative" | "balanced" | "aggressive"
            "scan_interval_min": 5,
            "max_positions": 4,
            "position_size_pct": 25.0,
            "stop_loss_pct": 2.5,
            "take_profit_pct": 6.0,
            "min_score": 60,
            "timeframe": "1h",
            # 물타기
            "auto_avg_down": True,
            "avg_down_threshold_pct": 3.0,
            "max_avg_down": 2,
            # 추매
            "auto_add": False,
            "add_threshold_pct": 3.0,
            "max_add": 1,
            # 트레일링 스탑
            "trailing_stop": True,
            "trailing_activate_pct": 4.0,   # 이 % 이익 도달 시 활성화
            "trailing_pct": 2.0,            # 고점 대비 이 % 하락 시 청산
            # AI 기능 개별 활성화
            "ai_entry_validation": True,   # 진입 신뢰도 AI 검증
            "ai_regime_detection": True,   # 시장 국면 자동 감지 + 스타일 조정
            "ai_loss_analysis": True,      # 연속 손절 자기 분석
            "ai_exit_assist": True,        # 이익 구간 청산 타이밍 보조
            # 포트폴리오 리스크
            "max_daily_loss_pct": 5.0,          # 일일 총자산 대비 최대 손실 (%)
            "max_portfolio_exposure_pct": 90.0,  # 최대 투자 비중 (%)
            "correlation_threshold": 0.85,       # 종목 간 상관계수 진입 차단 임계값
            "mdd_limit_pct": 20.0,              # MDD 이 값(%) 초과 시 봇 자동 중지
            # ── 부분 청산 (TODO 22) ────────────────────────────────────────────
            "partial_exit_enabled": False,      # 부분 청산 활성화
            "partial_exit_ratio": 0.4,          # TP 트리거 도달 시 청산 비율 (40%)
            "partial_exit_trigger_pct": 0.6,    # avg→TP 거리의 N% 도달 시 발동 (60%)
            # ── 피라미딩 ──────────────────────────────────────────────────────
            "pyramid_enabled": False,      # 피라미딩 활성화
            "pyramid_threshold_pct": 3.0,  # 발동 수익률 (%)
            "max_pyramid": 2,              # 최대 횟수
            # ── 선물 거래 설정 ────────────────────────────────────────────────
            "market_type": "spot",         # "spot" | "futures"
            "leverage": 5,                 # 레버리지 배수 (1~20)
            "margin_mode": "cross",        # "cross" | "isolated"
            # ── 자동 스타일 전환 허용 목록 ────────────────────────────────────
            "allowed_styles": ["scalping", "short", "mid", "long"],
        }

    # ── 프로퍼티 ─────────────────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def is_paused(self) -> bool:
        return self._paused

    @property
    def _quote_currency(self) -> str:
        """업비트 → KRW, Binance/Bybit 현물/선물 → USDT"""
        return "KRW" if self.settings.get("exchange_id", "upbit") == "upbit" else "USDT"

    @property
    def _is_futures(self) -> bool:
        return self.settings.get("market_type", "spot") == "futures"

    @property
    def _btc_symbol(self) -> str:
        return f"BTC/{self._quote_currency}"

    # ── 시작 / 중지 ─────────────────────────────────────────────────────────

    def start(self, settings: Optional[dict] = None):
        if self._running:
            return
        if settings:
            self.settings.update({k: v for k, v in settings.items() if k in self.settings})

        self._running = True
        self._started_at = datetime.now(KST)
        exchange_id = self.settings.get("exchange_id", "upbit")

        if self._is_futures:
            # 선물 모드: BinanceFuturesConnector 초기화 (시세 조회용)
            from ..core.config import get_settings
            cfg = get_settings()
            self._futures_connector = BinanceFuturesConnector(
                api_key=cfg.BINANCE_API_KEY,
                secret=cfg.BINANCE_SECRET,
                testnet=cfg.BINANCE_FUTURES_TESTNET,
            )
            # ExchangeConnector도 시세/OHLCV 조회에 활용 (binance spot)
            self._connector = ExchangeConnector(exchange_id="binance", is_paper=True)
            # 선물 잔고 초기화 (기존 잔고 유지)
            if self._futures_broker.usdt_balance <= 0:
                self._futures_broker.usdt_balance = 1_000.0
        else:
            # 현물 모드
            self._connector = ExchangeConnector(exchange_id=exchange_id, is_paper=True)
            # 거래소별 수수료율 갱신
            from ..exchange.connector import EXCHANGE_FEES
            self._broker.fee_rate = EXCHANGE_FEES.get(exchange_id, 0.001)
            # 거래소별 기본 잔고 (기존 잔고가 해당 quote로 있으면 유지)
            quote = self._quote_currency
            DEFAULT_BALANCE = {"KRW": 1_000_000, "USDT": 1_000}
            existing = self._broker.balance.get(quote, DEFAULT_BALANCE.get(quote, 1_000))
            self._broker.balance = {quote: existing}

        scan_interval = self.settings.get("scan_interval_min") or \
                        TIMEFRAME_MINUTES.get(self.settings["timeframe"], 60)

        # ── 스캔 + 신규 진입 사이클 (APScheduler) ───────────────────
        self._scheduler.add_job(
            self._cycle,
            IntervalTrigger(minutes=scan_interval),
            id="auto_bot_cycle",
            replace_existing=True,
            next_run_time=datetime.now(),
        )
        if not self._scheduler.running:
            self._scheduler.start()

        # ── 실시간 가격 모니터 (asyncio 태스크, 0.5초 루프) ──────────
        try:
            loop = asyncio.get_running_loop()
            self._price_task = loop.create_task(self._price_monitor_loop())
        except RuntimeError:
            logger.warning("AutoTradeBot: 실시간 모니터 태스크 생성 실패 (이벤트 루프 없음)")

        logger.info(
            f"AutoTradeBot started  스캔={scan_interval}m  "
            f"타임프레임={self.settings['timeframe']}  가격모니터=WS 실시간"
        )

    def stop(self):
        if not self._running:
            return
        self._running = False
        self._paused = False
        self._started_at = None
        # asyncio 가격 모니터 태스크 취소
        if self._price_task and not self._price_task.done():
            self._price_task.cancel()
        self._price_task = None
        # APScheduler 스캔 잡 제거
        try:
            if self._scheduler.running and self._scheduler.get_job("auto_bot_cycle"):
                self._scheduler.remove_job("auto_bot_cycle")
        except Exception:
            pass
        # 선물 커넥터 정리
        if self._futures_connector:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self._futures_connector.close())
                else:
                    loop.run_until_complete(self._futures_connector.close())
            except Exception:
                pass
            self._futures_connector = None
        logger.info("AutoTradeBot stopped")

    def pause(self):
        """일시정지: 신규 진입·스캔 차단. 기존 포지션 SL/TP 모니터는 유지."""
        if not self._running or self._paused:
            return
        self._paused = True
        logger.info("AutoTradeBot paused — 신규 진입 차단, 포지션 모니터 유지")

    def resume(self):
        """일시정지 해제: 정상 매매로 복귀."""
        if not self._running or not self._paused:
            return
        self._paused = False
        logger.info("AutoTradeBot resumed")

    async def full_stop(self, is_paper: bool = True):
        """
        중단:
        - 모의: 전체 포지션 현재가 청산 → 잔고·로그 초기화 → 봇 정지
        - 실거래: 전체 포지션 청산 → 봇 정지 (잔고 유지)
        """
        if not self._running:
            return

        # 1. 선물 포지션 청산
        if self._is_futures:
            for symbol in list(self._futures_positions.keys()):
                pos = self._futures_positions.get(symbol)
                if not pos:
                    continue
                price = pos.get("current_price") or pos["entry_price"]
                if self._futures_connector:
                    try:
                        price = await asyncio.wait_for(
                            self._futures_connector.get_mark_price(symbol), timeout=10
                        )
                    except Exception:
                        pass
                await self._close_futures_position(symbol, price, "full_stop")
            if is_paper:
                self._futures_broker.usdt_balance = 1_000.0
                self._futures_broker.positions.clear()
                self._trade_log.clear()
                self._scan_results = []
                self._last_scan_at = None
                self._portfolio_risk = PortfolioRiskManager()
                self._consecutive_losses = 0
                self._analysis_log.clear()
                logger.info("AutoTradeBot full_stop: 선물 모의 잔고·기록 초기화 완료")
            else:
                logger.info("AutoTradeBot full_stop: 선물 포지션 전량 청산 완료")
            self.stop()
            return

        # 1. 현물 포지션 청산 (현재가 기준)
        symbols = list(self._positions.keys())
        for symbol in symbols:
            pos = self._positions.get(symbol)
            if not pos:
                continue
            price = pos.get("current_price") or pos["avg_price"]
            if self._connector:
                try:
                    ticker = await asyncio.wait_for(
                        self._connector.fetch_ticker(symbol), timeout=10
                    )
                    price = ticker["last"]
                except Exception as e:
                    logger.warning(f"full_stop: {symbol} 현재가 조회 실패 → 평균단가 사용 ({e})")
            await self._close_position(symbol, price, "full_stop")

        # 2. 모의: 잔고·로그·스캔 결과 초기화
        if is_paper:
            quote = self._quote_currency
            DEFAULT_BALANCE = {"KRW": 1_000_000, "USDT": 1_000}
            self._broker.balance = {quote: DEFAULT_BALANCE.get(quote, 1_000)}
            self._trade_log.clear()
            self._scan_results = []
            self._last_scan_at = None
            self._portfolio_risk = PortfolioRiskManager()
            self._consecutive_losses = 0
            self._cooldown_until = 0.0
            self._reentry_blacklist.clear()
            self._last_regime_at = 0.0
            self._current_regime = {"regime": "ranging", "style": "short", "min_score_delta": 0, "reason": "초기화", "strategy_mode": "momentum"}
            self._strategy_performance = {
                k: {"wins": 0, "losses": 0, "total_pnl": 0.0}
                for k in self._strategy_performance
            }
            self._analysis_log.clear()
            logger.info("AutoTradeBot full_stop: 모의 잔고·기록 초기화 완료")
        else:
            logger.info("AutoTradeBot full_stop: 실거래 포지션 전량 청산 완료")

        # 3. 봇 정지
        self.stop()

    def update_settings(self, new_settings: dict):
        # 스타일 변경 시 프리셋 + 투자 성향(risk_profile)을 함께 적용
        if "trading_style" in new_settings:
            style = new_settings["trading_style"]
            preset = TRADING_STYLE_PRESETS.get(style)
            if preset:
                profile = new_settings.get("risk_profile") or self.settings.get("risk_profile", "balanced")
                applied = apply_risk_profile(preset, profile)
                for k, v in applied.items():
                    if k != "label" and k in self.settings:
                        self.settings[k] = v
                self.settings["trading_style"] = style
        # 개별 오버라이드
        for k, v in new_settings.items():
            if k != "trading_style" and k in self.settings:
                self.settings[k] = v

        # 봇 실행 중이면 스캔 주기를 즉시 재적용 (기존 포지션 SL/TP는 유지)
        if self._running and self._scheduler.running:
            new_interval = self.settings.get("scan_interval_min") or \
                           TIMEFRAME_MINUTES.get(self.settings["timeframe"], 60)
            try:
                self._scheduler.reschedule_job(
                    "auto_bot_cycle",
                    trigger=IntervalTrigger(minutes=new_interval),
                )
                logger.info(f"AutoTradeBot: 설정 변경 적용 — 스캔 주기={new_interval}분 (기존 포지션 SL/TP 유지)")
            except Exception as e:
                logger.warning(f"AutoTradeBot: 스캔 주기 재설정 실패: {e}")

    def set_paper_balance(self, krw: float):
        """모의거래 잔고 직접 설정 (KRW 또는 USDT) — 봇 중지 상태에서만 허용"""
        if self.is_running:
            raise ValueError("봇 실행 중에는 잔고를 수정할 수 없습니다. 먼저 봇을 중지해 주세요.")
        if krw < 0:
            raise ValueError("잔고는 0 이상이어야 합니다.")
        if self._is_futures:
            self._futures_broker.usdt_balance = krw
            logger.info(f"AutoTradeBot: 선물 모의 잔고 변경 → {krw:,.4f} USDT")
        else:
            quote = self._quote_currency
            self._broker.balance[quote] = krw
            logger.info(f"AutoTradeBot: 모의거래 잔고 변경 → {krw:,.0f} {quote}")

    # ── 실시간 가격 모니터 ───────────────────────────────────────────────────

    async def _price_monitor_loop(self):
        """
        REST 폴링 기반 가격 모니터 (모든 거래소 공통, 1초 간격).
        업비트 WebSocket 직접 연결은 환경에 따라 DNS 문제가 발생할 수 있어
        안정성 우선으로 REST 방식으로 통합.
        """
        await self._rest_price_monitor_loop()

    async def _rest_price_monitor_loop(self):
        """REST 폴링 가격 모니터 (모든 거래소 공통, 1초 간격)."""
        while self._running:
            try:
                # 현물 포지션 업데이트
                if self._positions and self._connector:
                    for symbol in list(self._positions.keys()):
                        try:
                            ticker = await asyncio.wait_for(
                                self._connector.fetch_ticker(symbol), timeout=5
                            )
                            price = ticker.get("last") or ticker.get("close", 0)
                            if price:
                                await self._handle_price_update(symbol, price)
                        except Exception:
                            pass

                # 선물 포지션 업데이트
                if self._futures_positions and self._futures_connector:
                    for symbol in list(self._futures_positions.keys()):
                        try:
                            price = await asyncio.wait_for(
                                self._futures_connector.get_mark_price(symbol), timeout=5
                            )
                            if price:
                                pos = self._futures_positions.get(symbol)
                                if pos:
                                    pos["current_price"] = price
                                    self._futures_broker.update_unrealized_pnl(symbol, price)
                                    fp = self._futures_broker.positions.get(symbol)
                                    if fp:
                                        invested = pos["initial_margin"]
                                        pos["unrealized_pnl_usdt"] = round(fp["unrealized_pnl"], 4)
                                        pos["unrealized_pnl_pct"]  = round(
                                            fp["unrealized_pnl"] / invested * 100, 2
                                        ) if invested > 0 else 0.0
                                    # 즉각 SL/TP 체크
                                    await self._check_single_futures_position(symbol, price)
                        except Exception:
                            pass

                await asyncio.sleep(1)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"AutoTradeBot REST 모니터 오류: {e}")
                await asyncio.sleep(5)

    async def _check_single_futures_position(self, symbol: str, price: float):
        """선물 단일 포지션 SL/TP + 청산가 체크 (REST 모니터용)."""
        pos = self._futures_positions.get(symbol)
        if pos is None:
            return
        side = pos["side"]
        sl   = pos["stop_loss_price"]
        tp   = pos["take_profit_price"]

        if side == "long":
            if price <= sl:
                await self._close_futures_position(symbol, price, "stop_loss")
                return
            if price >= tp:
                await self._close_futures_position(symbol, price, "take_profit")
                return
        else:
            if price >= sl:
                await self._close_futures_position(symbol, price, "stop_loss")
                return
            if price <= tp:
                await self._close_futures_position(symbol, price, "take_profit")
                return

        liq = pos.get("liquidation_price")
        if liq and liq > 0:
            distance_pct = abs(price - liq) / price * 100
            if distance_pct < 5.0:
                logger.warning(f"[청산가 경고] {symbol} {distance_pct:.1f}% — 강제 청산")
                await self._close_futures_position(symbol, price, "liquidation_warning")

    async def _handle_price_update(self, symbol: str, price: float):
        """REST 폴링용 가격 업데이트 처리 (WS _handle_ws_trade 와 동일 로직)."""
        pos = self._positions.get(symbol)
        if pos is None:
            return
        avg = pos["avg_price"]

        if price > pos["highest_price"]:
            pos["highest_price"] = price

        pnl_pct = (price - avg) / avg * 100

        if self.settings.get("trailing_stop"):
            t_activate = pos.get("trailing_activate_pct", self.settings["trailing_activate_pct"])
            t_pct      = pos.get("trailing_pct",          self.settings["trailing_pct"])
            if not pos["trailing_active"] and pnl_pct >= t_activate:
                pos["trailing_active"] = True
                pos["take_profit_price"] = float("inf")
            if pos["trailing_active"]:
                trail_price = pos["highest_price"] * (1 - t_pct / 100)
                if price <= trail_price:
                    await self._close_position(symbol, price, "trailing_stop")
                    return

        # T3: 손익분기점 SL 이동 — 수익 +1% 도달 시 SL → 진입가 (원금 보호)
        # 물타기 여유가 남아 있으면 스킵 — BE SL이 물타기 발동 전 손절을 유발하는 충돌 방지
        # 물타기를 모두 소진했거나 비활성일 때만 BE SL 적용
        _avg_down_remaining = (
            self.settings.get("auto_avg_down")
            and pos.get("avg_down_count", 0) < self.settings.get("max_avg_down", 2)
        )
        if (pnl_pct >= 1.0
                and not pos["trailing_active"]
                and pos["stop_loss_price"] < avg
                and not _avg_down_remaining):
            pos["stop_loss_price"] = avg
            logger.debug(f"AutoBot BE SL 이동 {symbol}: SL → 진입가 {avg:,.0f}")

        if price <= pos["stop_loss_price"]:
            await self._close_position(symbol, price, "stop_loss")
        elif not pos.get("trailing_active") and price >= pos["take_profit_price"]:
            await self._close_position(symbol, price, "take_profit")
        else:
            pos["current_price"] = price
            total_amount   = pos["total_amount"]
            entry_fees     = pos.get("total_fee_krw", 0)
            est_exit_fee   = price * total_amount * self._broker.fee_rate
            net_pnl        = (price - avg) * total_amount - entry_fees - est_exit_fee
            total_invested = avg * total_amount
            pos["unrealized_pnl_krw"] = round(net_pnl)
            pos["unrealized_pnl_pct"] = round(net_pnl / total_invested * 100, 2) if total_invested else 0

    async def _ws_price_monitor(self):
        """
        업비트 WebSocket v1 체결가(trade) 구독.
        포지션 변경 시 구독 종목을 자동 갱신.
        """
        import aiohttp
        import json
        import uuid

        url = "wss://api.upbit.com/websocket/v1"
        last_symbols: set[str] = set()

        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(url, heartbeat=20, receive_timeout=60) as ws:
                logger.info("AutoTradeBot WS: 연결 완료")

                recv_task = asyncio.create_task(self._ws_recv_loop(ws))
                try:
                    while self._running and not recv_task.done():
                        cur = set(self._positions.keys())
                        if cur != last_symbols:
                            if cur:
                                codes = [
                                    f"{s.split('/')[1]}-{s.split('/')[0]}"
                                    for s in cur
                                ]
                                await ws.send_str(json.dumps([
                                    {"ticket": str(uuid.uuid4())},
                                    {"type": "trade", "codes": codes},
                                    {"format": "SIMPLE"},
                                ]))
                                logger.info(f"AutoTradeBot WS: 구독 갱신 {codes}")
                            last_symbols = cur
                        await asyncio.sleep(0.3)
                finally:
                    recv_task.cancel()
                    try:
                        await recv_task
                    except asyncio.CancelledError:
                        pass

                logger.info("AutoTradeBot WS: 연결 종료")

    async def _ws_recv_loop(self, ws):
        """WebSocket 체결 메시지 수신 루프"""
        import json
        import aiohttp
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.BINARY:
                try:
                    data = json.loads(msg.data.decode("utf-8"))
                    await self._handle_ws_trade(data)
                except Exception as e:
                    logger.debug(f"AutoTradeBot WS parse: {e}")
            elif msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSED):
                break

    async def _handle_ws_trade(self, data: dict):
        """체결 메시지 → 즉시 SL/TP + 트레일링 스탑 판단"""
        if data.get("ty") != "trade":
            return
        code: str = data.get("cd", "")    # 예: KRW-BTC
        price: float = data.get("tp", 0)  # 체결가
        if not code or not price:
            return

        # KRW-BTC → BTC/KRW
        parts = code.split("-", 1)
        if len(parts) != 2:
            return
        symbol = f"{parts[1]}/{parts[0]}"

        pos = self._positions.get(symbol)
        if pos is None:
            return

        avg = pos["avg_price"]

        # ── 고점 갱신 ────────────────────────────────────────────────────────
        if price > pos["highest_price"]:
            pos["highest_price"] = price

        # ── 부분 청산 체크 (TODO 22) ─────────────────────────────────────────
        await self._check_partial_exit(symbol, price)
        if symbol not in self._positions:  # 부분 청산 중 포지션 소멸 방어
            return

        # ── 트레일링 스탑 ────────────────────────────────────────────────────
        pnl_pct = (price - avg) / avg * 100

        if self.settings.get("trailing_stop"):
            # 포지션별 파라미터 우선, 없으면 글로벌 설정
            t_activate = pos.get("trailing_activate_pct", self.settings["trailing_activate_pct"])
            t_pct      = pos.get("trailing_pct",          self.settings["trailing_pct"])

            # 활성화 조건: 목표 이익 도달 → TP 상한 제거 후 고점 추적 모드
            if not pos["trailing_active"] and pnl_pct >= t_activate:
                pos["trailing_active"] = True
                pos["take_profit_price"] = float("inf")  # TP 상한 제거
                logger.info(
                    f"AutoBot 트레일링 활성화 {symbol}  "
                    f"pnl={pnl_pct:.1f}%  고점={pos['highest_price']:,.0f}₩"
                )

            # 트레일링 활성화 상태 → 고점 대비 N% 하락 시 청산
            if pos["trailing_active"]:
                trail_price = pos["highest_price"] * (1 - t_pct / 100)
                if price <= trail_price:
                    await self._close_position(symbol, price, "trailing_stop")
                    return

        # T3: 손익분기점 SL 이동 — 수익 +1% 도달 시 SL → 진입가 (원금 보호)
        # 물타기 여유가 남아 있으면 스킵 (물타기 발동 전 BE SL 손절 충돌 방지)
        _avg_down_remaining = (
            self.settings.get("auto_avg_down")
            and pos.get("avg_down_count", 0) < self.settings.get("max_avg_down", 2)
        )
        if (pnl_pct >= 1.0
                and not pos["trailing_active"]
                and pos["stop_loss_price"] < avg
                and not _avg_down_remaining):
            pos["stop_loss_price"] = avg
            logger.debug(f"AutoBot BE SL 이동 {symbol}: SL → 진입가 {avg:,.0f}")

        # ── 일반 SL / TP ─────────────────────────────────────────────────────
        if price <= pos["stop_loss_price"]:
            await self._close_position(symbol, price, "stop_loss")
        elif not pos.get("trailing_active") and price >= pos["take_profit_price"]:
            await self._close_position(symbol, price, "take_profit")
        else:
            pos["current_price"] = price
            # 미실현 손익 = 평가손익 - 진입수수료 누적 - 예상 청산수수료
            total_amount = pos["total_amount"]
            entry_fees   = pos.get("total_fee_krw", 0)
            est_exit_fee = price * total_amount * self._broker.fee_rate
            net_pnl_krw  = (price - avg) * total_amount - entry_fees - est_exit_fee
            total_invested = avg * total_amount
            pos["unrealized_pnl_krw"] = round(net_pnl_krw)
            pos["unrealized_pnl_pct"] = round(net_pnl_krw / total_invested * 100, 2) if total_invested > 0 else 0.0

    # ── 메인 사이클 ─────────────────────────────────────────────────────────

    async def _cycle(self):
        if self._scan_in_progress:
            return
        self._scan_in_progress = True
        try:
            # ── MDD 자동 거래 중단 체크 (TODO 13) ─────────────────────────
            if len(self._trade_log) >= 10:
                perf = calc_performance(self._trade_log)
                mdd_limit = self.settings.get("mdd_limit_pct", 20.0)
                if perf["max_drawdown_pct"] >= mdd_limit:
                    logger.warning(
                        f"AutoBot MDD {perf['max_drawdown_pct']:.1f}% ≥ 한도 {mdd_limit}% "
                        f"— 봇 자동 중지 (VaR95={perf['var_95']:.2f}%)"
                    )
                    self.stop()
                    return

            if self._is_futures:
                await self._cycle_futures()
            else:
                await self._cycle_spot()
        except Exception as e:
            logger.error(f"AutoTradeBot cycle error: {e}", exc_info=True)
        finally:
            self._scan_in_progress = False

    async def _cycle_spot(self):
        """현물 매매 사이클 (기존 로직)"""
        # 국면 감지를 먼저 실행 → 스타일 변경 후 스캔
        await self._run_regime_detection()
        # 성과 피드백: 30분마다 실제 승률·R:R로 min_score 자동 보정
        await self._run_performance_feedback()

        exchange_id = self.settings.get("exchange_id", "upbit")
        global_style = self.settings.get("trading_style", "short")

        # 메인 스캔 + 5m 초단타 병렬 스캔 (글로벌 스타일이 이미 scalping이면 별도 스캔 불필요)
        if global_style != "scalping":
            scan_results, scalping_scan = await asyncio.gather(
                scan_market(timeframe=self.settings["timeframe"], style=global_style, exchange_id=exchange_id),
                scan_market(timeframe="5m", style="scalping", exchange_id=exchange_id),
            )
        else:
            scan_results = await scan_market(timeframe="5m", style="scalping", exchange_id=exchange_id)
            scalping_scan = []

        # DB 전략 조건 평가 → 스캔 결과에 병합
        # 심볼이 이미 스캔됐으면 점수를 DB 후보값으로 높이고 신호를 병합.
        # 이전 코드(심볼 중복 시 무시)는 일반 스캔 점수가 낮아 진입이 영원히 차단되는 버그 유발.
        db_candidates = await self._eval_db_strategies(scan_results)
        if db_candidates:
            symbol_to_idx = {r["symbol"]: i for i, r in enumerate(scan_results)}
            for c in db_candidates:
                if c["symbol"] in symbol_to_idx:
                    idx = symbol_to_idx[c["symbol"]]
                    existing = scan_results[idx]
                    scan_results[idx] = {
                        **existing,
                        "score":    max(existing["score"], c["score"]),
                        "signals":  existing.get("signals", []) + c.get("signals", []),
                        "sl_pct":   c["sl_pct"] or existing.get("sl_pct"),
                        "tp_pct":   c["tp_pct"] or existing.get("tp_pct"),
                    }
                else:
                    scan_results.append(c)

        self._scan_results = scan_results
        self._last_scan_at = datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")

        await self._check_positions(scan_results)

        if not self._paused and len(self._positions) < self.settings["max_positions"]:
            import time as _ct
            # T2: 연속 손절 쿨다운 체크
            if _ct.time() < self._cooldown_until:
                remaining_min = int((self._cooldown_until - _ct.time()) / 60)
                logger.info(f"AutoBot 쿨다운 중 — 신규 진입 전면 차단 (잔여 {remaining_min}분)")
            else:
                # 상관관계 체크용 종가 캐시 갱신 (현재 보유 + 스캔 상위 후보)
                top_candidates = [r["symbol"] for r in scan_results[:10]]
                await self._refresh_close_cache(top_candidates)
                await self._enter_from_scan(scan_results)

                # 초단타 병렬 진입 — 글로벌 스타일과 무관하게 5m 강세 종목 최대 2개
                if scalping_scan and len(self._positions) < self.settings["max_positions"]:
                    await self._enter_scalping_positions(scalping_scan)

    async def _cycle_futures(self):
        """선물 매매 사이클"""
        if not self._futures_connector:
            return

        scan_results = await scan_futures_market(
            connector=self._futures_connector,
            timeframe=self.settings["timeframe"],
            style=self.settings["trading_style"],
        )
        self._scan_results = scan_results
        self._last_scan_at = datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")

        # 펀딩비 체크 (8시간마다)
        import time as _t
        if _t.time() - self._last_funding_check >= 28800:
            await self._check_funding_rates()
            self._last_funding_check = _t.time()

        # 기존 선물 포지션 점검
        await self._check_futures_positions(scan_results)

        # 신규 선물 포지션 진입
        if not self._paused and len(self._futures_positions) < self.settings["max_positions"]:
            await self._enter_futures_from_scan(scan_results)

    # ── TODO 10: 포트폴리오 상관관계 캐시 ────────────────────────────────────

    async def _refresh_close_cache(self, symbols: list[str]):
        """
        상관관계 계산용 1h 종가 캐시 업데이트.
        현재 보유 종목 + 전달된 종목 리스트에 대해 60봉 1h OHLCV 조회.
        캐시는 사이클마다 갱신되어 최신 상태 유지.
        """
        target = set(self._positions.keys()) | set(symbols)
        for sym in target:
            try:
                df = await asyncio.wait_for(
                    self._connector.fetch_ohlcv(sym, "1h", limit=60),
                    timeout=8,
                )
                if df is not None and len(df) >= 10:
                    self._close_cache[sym] = [float(x) for x in df["close"].tolist()]
            except Exception:
                pass

    # ── TODO 2: AI 시장 국면 감지 ────────────────────────────────────────────

    def _detect_regime_rules(
        self,
        btc_closes: list[float],
        btc_rsi: float,
        btc_volume_ratio: float,
        btc_adx: float = 0.0,
    ) -> dict:
        """
        규칙 기반 시장 국면 감지 (AI 없이 항상 동작).
        BTC 기술 지표로 국면을 판단하고 최적 매매 스타일을 반환.

        국면 판단 기준:
          trending  : 20봉 변화 +5% 초과, RSI 50~75 → short/mid
          bull_run  : 20봉 변화 +10% 초과, RSI 60+ → mid/long
          volatile  : RSI < 28 or > 78, 또는 거래량 2.5x+ → scalping
          downtrend : 20봉 변화 -8% 미만 → long (반등 대기) + 점수 +5
          ranging   : 그 외 → short

        strategy_mode:
          mean_reversion : ADX < 20 (횡보장) → BB 하단 반등 매수 전략
          momentum       : ADX >= 20 (추세장) → 기존 모멘텀 전략
        """
        if len(btc_closes) < 20:
            return {"regime": "ranging", "style": "short", "min_score_delta": 0, "reason": "데이터 부족", "strategy_mode": "momentum"}

        change_20 = (btc_closes[-1] - btc_closes[-20]) / btc_closes[-20] * 100

        # 단기 변동성: 최근 5봉 최고/최저 범위
        recent5 = btc_closes[-5:]
        volatility_5 = (max(recent5) - min(recent5)) / min(recent5) * 100 if min(recent5) > 0 else 0

        if btc_rsi > 78 or (btc_volume_ratio >= 2.5 and volatility_5 > 3.0):
            regime, style, delta = "volatile", "scalping", -5
            reason = f"과열 (RSI {btc_rsi:.0f}, 변동 {volatility_5:.1f}%, 거래량 {btc_volume_ratio:.1f}x)"
        elif change_20 >= 10 and btc_rsi >= 60:
            regime, style, delta = "trending", "mid", +5
            reason = f"강한 상승추세 (20봉 {change_20:+.1f}%, RSI {btc_rsi:.0f})"
        elif change_20 >= 5 and btc_rsi >= 50:
            regime, style, delta = "trending", "short", +3
            reason = f"상승추세 (20봉 {change_20:+.1f}%, RSI {btc_rsi:.0f})"
        elif change_20 <= -8:
            # 하락추세에서 "long" 스타일(SL -12%)은 손실 폭을 키움.
            # scalping(SL -1%)으로 손실을 최소화하고 반등 신호에만 소량 진입.
            regime, style, delta = "downtrend", "scalping", +15
            reason = f"하락추세 (20봉 {change_20:+.1f}%, RSI {btc_rsi:.0f}) → 스캘핑 전환, 진입 기준 +15"
        elif btc_rsi < 28:
            regime, style, delta = "volatile", "scalping", 0
            reason = f"과매도 반등 구간 (RSI {btc_rsi:.0f})"
        elif change_20 <= -3 and btc_rsi < 45:
            regime, style, delta = "ranging", "short", +3
            reason = f"약세 횡보 (20봉 {change_20:+.1f}%, RSI {btc_rsi:.0f})"
        else:
            regime, style, delta = "ranging", "short", 0
            reason = f"횡보 (20봉 {change_20:+.1f}%, RSI {btc_rsi:.0f})"

        # ADX < 20 이면 횡보장 → 평균 회귀 전략 활성화
        if btc_adx > 0 and btc_adx < 20:
            strategy_mode = "mean_reversion"
            reason += f", ADX {btc_adx:.1f} (횡보장→평균회귀)"
        else:
            strategy_mode = "momentum"
            if btc_adx >= 20:
                reason += f", ADX {btc_adx:.1f}"

        return {"regime": regime, "style": style, "min_score_delta": delta, "reason": reason, "strategy_mode": strategy_mode}

    @staticmethod
    def _calc_rsi(closes: list[float], period: int = 14) -> float:
        """closes 리스트에서 단순 RSI 계산 (scan_results 의존성 없음)"""
        if len(closes) < period + 1:
            return 50.0
        deltas = [closes[i] - closes[i - 1] for i in range(-period, 0)]
        gains = sum(d for d in deltas if d > 0)
        losses = sum(-d for d in deltas if d < 0)
        avg_gain = gains / period
        avg_loss = losses / period
        if avg_loss == 0:
            return 100.0
        return round(100 - 100 / (1 + avg_gain / avg_loss), 2)

    async def _run_regime_detection(self):
        """
        BTC 지표 기반 국면 감지. 15분 이내 재호출 차단.
        규칙 기반 분석은 항상 실행, AI 설정 시 LLM 결과로 보완.
        국면 변경 시 trading_style / min_score 자동 조정.
        스캔 이전에 호출되어 올바른 스타일로 스캔하도록 보장.
        """
        import time
        if not self.settings.get("ai_regime_detection", True):
            return
        if time.time() - self._last_regime_at < 900:   # 15분 이내면 스킵
            return

        try:
            btc_df = await asyncio.wait_for(
                self._connector.fetch_ohlcv(self._btc_symbol, self.settings["timeframe"], limit=25),
                timeout=12,
            )
            if btc_df is None or len(btc_df) < 20:
                logger.debug("AutoBot 국면 감지: BTC 데이터 부족, 스킵")
                return

            btc_closes = [float(x) for x in btc_df["close"].tolist()]
            vol_series = btc_df["volume"]
            vol_avg = float(vol_series.iloc[-21:-1].mean()) if len(vol_series) >= 21 else 1.0
            vol_now  = float(vol_series.iloc[-1])
            btc_volume_ratio = round(vol_now / vol_avg, 2) if vol_avg > 0 else 1.0

            btc_rsi = self._calc_rsi(btc_closes)

            # BTC ADX 계산 (횡보장 감지용, TODO 25)
            btc_adx = 0.0
            try:
                import pandas_ta as ta
                adx_df = ta.adx(btc_df["high"], btc_df["low"], btc_df["close"], length=14)
                if adx_df is not None and not adx_df.empty:
                    adx_col = [c for c in adx_df.columns if c.startswith("ADX_")]
                    if adx_col:
                        adx_series = adx_df[adx_col[0]].dropna()
                        if not adx_series.empty:
                            btc_adx = float(adx_series.iloc[-1])
            except Exception:
                pass

            # ── 1단계: 규칙 기반 국면 판단 (항상 실행) ───────────────────────
            regime = self._detect_regime_rules(btc_closes, btc_rsi, btc_volume_ratio, btc_adx)

            # ── 2단계: AI 보완 (설정 + 사용 가능 시) ─────────────────────────
            if ai_analyst.is_ai_available():
                try:
                    ai_regime = await ai_analyst.detect_regime(
                        btc_closes=btc_closes,
                        btc_rsi=btc_rsi,
                        btc_volume_ratio=btc_volume_ratio,
                    )
                    regime = ai_regime  # AI 결과 우선
                except Exception:
                    pass  # 규칙 기반 결과 유지

            import time as _t
            self._last_regime_at = _t.time()

            old_regime        = self._current_regime.get("regime")
            old_style         = self._current_regime.get("style")
            old_strategy_mode = self._current_regime.get("strategy_mode", "momentum")
            old_delta         = self._current_regime.get("min_score_delta", 0)
            self._current_regime = regime

            new_style         = regime["style"]
            new_strategy_mode = regime.get("strategy_mode", "momentum")
            delta             = regime["min_score_delta"]
            changed           = []

            # 사용자 허용 목록 필터 — 허용되지 않은 스타일이면 가장 가까운 허용 스타일로 대체
            _style_order = ["scalping", "short", "mid", "long"]
            allowed = self.settings.get("allowed_styles") or _style_order
            if new_style not in allowed:
                idx = _style_order.index(new_style) if new_style in _style_order else 1
                # 인접한 허용 스타일을 가까운 순서로 탐색
                for offset in range(1, len(_style_order)):
                    for candidate in [_style_order[idx - offset] if idx - offset >= 0 else None,
                                      _style_order[idx + offset] if idx + offset < len(_style_order) else None]:
                        if candidate and candidate in allowed:
                            logger.info(f"AutoBot 국면: 스타일 {new_style} 미허용 → {candidate}로 대체")
                            new_style = candidate
                            regime = {**regime, "style": new_style}
                            self._current_regime = regime
                            break
                    else:
                        continue
                    break

            if new_strategy_mode != old_strategy_mode:
                changed.append(f"전략모드 {old_strategy_mode}→{new_strategy_mode}")

            if new_style != self.settings.get("trading_style") and new_style in TRADING_STYLE_PRESETS:
                self.update_settings({"trading_style": new_style})
                changed.append(f"스타일 {old_style}→{new_style}")

            # delta는 절대값(이전 delta를 되돌리고 새 delta를 적용)으로 처리.
            # 누적 가산 방지: 같은 국면이 15분마다 반복돼도 min_score가 계속 오르지 않음.
            # 단, update_settings가 min_score를 새 스타일 기본값으로 리셋한 뒤 delta를 빼므로
            # 새 스타일의 preset base보다 낮아지지 않도록 floor를 걸어줌.
            delta_change = delta - old_delta
            if delta_change != 0:
                preset_floor = TRADING_STYLE_PRESETS.get(new_style, {}).get("min_score", 40)
                new_score = max(preset_floor, min(72, self.settings["min_score"] + delta_change))
                if new_score != self.settings["min_score"]:
                    self.settings["min_score"] = new_score
                    changed.append(f"최소점수 {new_score}")

            if changed or old_regime != regime["regime"]:
                log_entry = {
                    "at":      datetime.now(KST).strftime("%Y-%m-%d %H:%M KST"),
                    "type":    "regime_change",
                    "regime":  regime["regime"],
                    "style":   new_style,
                    "reason":  regime["reason"],
                    "changed": changed,
                }
                self._analysis_log.insert(0, log_entry)
                if len(self._analysis_log) > 20:
                    self._analysis_log.pop()
                src = "AI" if ai_analyst.is_ai_available() else "규칙"
                logger.info(
                    f"AutoBot 국면 [{src}]: {regime['regime']} "
                    f"{' | '.join(changed) if changed else '변경 없음'} — {regime['reason']}"
                )
        except Exception as e:
            logger.debug(f"AutoBot 국면 감지 오류: {e}")

    # ── TODO 9: DB 전략 조건 평가 ────────────────────────────────────────────

    async def _get_active_db_strategies(self) -> list[dict]:
        """DB에서 is_active=True 전략 로드 (5분 캐시)."""
        import time
        if time.time() - self._db_strategy_cache_ts < 300 and self._db_strategy_cache:
            return self._db_strategy_cache
        try:
            from ...core.database import AsyncSessionLocal
            from ...models.strategy import Strategy
            from sqlalchemy import select
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(Strategy).where(Strategy.is_active == True)
                )
                strategies = result.scalars().all()
                self._db_strategy_cache = [
                    {"id": s.id, "name": s.name, "config": s.config}
                    for s in strategies
                ]
                self._db_strategy_cache_ts = time.time()
                return self._db_strategy_cache
        except Exception as e:
            logger.debug(f"AutoBot: DB 전략 로드 실패: {e}")
            return []

    async def _eval_db_strategies(self, scan_results: list[dict]) -> list[dict]:
        """
        DB 전략 진입 조건 평가 → 신규 진입 후보 반환 (TODO 9).
        이미 스캔된 심볼은 중복 진입 방지 로직에서 제외됨.
        """
        if not self._connector:
            return []
        strategies = await self._get_active_db_strategies()
        if not strategies:
            return []

        from ..indicator.engine import evaluate_conditions

        extra: list[dict] = []
        for strat in strategies:
            cfg = strat.get("config", {})
            symbol   = cfg.get("symbol", "")
            tf       = cfg.get("timeframe", self.settings["timeframe"])
            entry_c  = cfg.get("entry_conditions", [])
            if not symbol or not entry_c:
                continue
            if symbol in self._positions:
                continue
            try:
                # 진입 조건에서 최대 지표 기간을 추출해 충분한 봉 수 확보
                max_period = max(
                    (max(
                        c.get("params", {}).get("length", 0),
                        c.get("params", {}).get("slow", 0),
                        c.get("params", {}).get("fast", 0),
                    ) for c in entry_c),
                    default=14,
                )
                fetch_limit = max(150, max_period * 2 + 50)
                df = await asyncio.wait_for(
                    self._connector.fetch_ohlcv(symbol, tf, limit=fetch_limit),
                    timeout=12,
                )
                if len(df) < 50 or not evaluate_conditions(df, entry_c):
                    continue
                risk = cfg.get("risk", {})
                # DB 전략 점수는 현재 min_score보다 항상 높게 설정해 진입 차단 방지.
                # 하드코딩 70은 conservative/AI 국면 상향으로 min_score가 70+가 되면 진입 불가 버그 유발.
                db_score = min(100, self.settings["min_score"] + 15)
                extra.append({
                    "symbol":             symbol,
                    "score":              db_score,
                    "rsi":                50.0,
                    "price":              float(df["close"].iloc[-1]),
                    "signals":            [f"DB전략 진입: {strat['name']}"],
                    "strategy_type":      f"db_{strat['id']}",
                    "strategy_label":     f"DB: {strat['name']}",
                    "sl_pct":             risk.get("stop_loss_pct"),
                    "tp_pct":             risk.get("take_profit_pct"),
                    "position_size_pct":  risk.get("position_size_pct"),  # 전략별 자본금 비율
                    "style":              self.settings["trading_style"],
                    "volume_ratio":       1.0,
                    "price_change_pct":   0.0,
                    "mtf_confirmed":      True,
                    "mtf_trend":          "neutral",
                })
                logger.info(f"AutoBot DB전략 신호: [{strat['name']}] {symbol}")
            except Exception as e:
                logger.debug(f"AutoBot DB전략 평가 오류 {symbol}: {e}")

        return extra

    async def run_scan_now(self):
        if self._scan_in_progress:
            return
        self._scan_in_progress = True
        try:
            results = await scan_market(
                timeframe=self.settings["timeframe"],
                style=self.settings["trading_style"],
                exchange_id=self.settings.get("exchange_id", "upbit"),
            )
            self._scan_results = results
            self._last_scan_at = datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")
        finally:
            self._scan_in_progress = False

    # ── 포지션 체크 (손절/익절 + 자동 물타기/추매 + 전략 재평가) ────────────

    async def _check_positions(self, scan_results: list[dict] | None = None):
        """
        스캔 사이클에서 호출. 무거운 로직만 담당:
          - 전략 재평가 (SL/TP 재조정)
          - 자동 물타기 / 추매
        SL/TP 체결 자체는 _realtime_position_check 에서 이미 처리됨.
        """
        if not self._connector:
            return

        scan_map: dict[str, dict] = {r["symbol"]: r for r in (scan_results or [])}

        for symbol in list(self._positions.keys()):
            pos = self._positions.get(symbol)
            if pos is None:
                continue
            try:
                # 스캔 사이클마다 REST로 현재가 갱신 (WS 보완)
                try:
                    ticker = await asyncio.wait_for(
                        self._connector.fetch_ticker(symbol), timeout=10
                    )
                    current_price = float(ticker["last"])
                    pos["current_price"] = current_price
                    # 미실현 손익 갱신
                    avg_p          = pos["avg_price"]
                    total_amount   = pos["total_amount"]
                    entry_fees     = pos.get("total_fee_krw", 0)
                    est_exit_fee   = current_price * total_amount * self._broker.fee_rate
                    net_pnl        = (current_price - avg_p) * total_amount - entry_fees - est_exit_fee
                    total_invested = avg_p * total_amount
                    pos["unrealized_pnl_krw"] = round(net_pnl)
                    pos["unrealized_pnl_pct"] = round(net_pnl / total_invested * 100, 2) if total_invested else 0.0
                except Exception:
                    current_price = pos.get("current_price") or pos["avg_price"]
                avg = pos["avg_price"]

                # ── 부분 청산 체크 (TODO 22) ──────────────────────────────────
                await self._check_partial_exit(symbol, current_price)
                if symbol not in self._positions:
                    continue

                # ── 전략 재평가 / 교체 ───────────────────────────────────────
                new_scan = scan_map.get(symbol)
                # 포지션별 스타일 우선 (AI가 선택한 값), 없으면 글로벌
                style = pos.get("position_style") or self.settings.get("trading_style", "short")
                if new_scan:
                    new_score = new_scan.get("score", 0)
                    new_type  = new_scan.get("strategy_type", "standard")
                    old_type  = pos.get("strategy_type", "standard")

                    if new_score >= self.settings["min_score"] and new_type != old_type:
                        # 신호가 충분하고 전략 유형이 바뀜 → SL/TP 재조정
                        sl_pct = new_scan.get("sl_pct") or self.settings["stop_loss_pct"]
                        tp_pct = new_scan.get("tp_pct") or self.settings["take_profit_pct"]
                        pos["strategy_type"]  = new_type
                        pos["strategy_label"] = new_scan.get("strategy_label", "표준")
                        pos["signals"]        = new_scan.get("signals", pos.get("signals", []))
                        pos["score"]          = new_score
                        pos["stop_loss_price"] = avg * (1 - sl_pct / 100)
                        # 전략 교체 시 포지션 스타일도 스캐너 분류 기반으로 재선택
                        new_pos_preset = TRADING_STYLE_PRESETS.get(style, TRADING_STYLE_PRESETS["short"])
                        pos["trailing_activate_pct"] = new_pos_preset["trailing_activate_pct"]
                        pos["trailing_pct"]          = new_pos_preset["trailing_pct"]
                        # 트레일링 활성화 상태면 TP는 건드리지 않음
                        if not pos.get("trailing_active"):
                            pos["take_profit_price"] = avg * (1 + tp_pct / 100)
                        logger.info(
                            f"AutoBot: 전략 교체 {symbol} {old_type}→{new_type} "
                            f"SL={sl_pct}% TP={tp_pct}%  점수={new_score}"
                        )

                    elif new_score < self.settings["min_score"] and not pos.get("trailing_active"):
                        # 신호 약화 → 이익이 충분한 경우에만 SL을 위로 당겨 이익 보호
                        # (너무 이른 SL 상향 방지: protect_pct*2 이상 이익일 때만 적용)
                        pnl_pct = pos.get("unrealized_pnl_pct", 0)
                        protect_pct = STYLE_SL_PROTECT_PCT.get(style, 0.5)
                        if pnl_pct >= protect_pct * 2:
                            new_sl = pos["avg_price"] * (1 + (pnl_pct - protect_pct) / 100)
                            if new_sl > pos["stop_loss_price"]:
                                pos["stop_loss_price"] = new_sl
                                logger.info(
                                    f"AutoBot: 신호 약화 → SL 상향 {symbol}  "
                                    f"pnl={pnl_pct:.1f}%  new_SL={new_sl:,.0f}₩"
                                )

                # ── TODO 4: AI 청산 타이밍 보조 (이익 중 포지션만) ──────────
                pnl_pct = pos.get("unrealized_pnl_pct", 0)
                min_pnl_for_ai = {"scalping": 0.8, "short": 1.5, "mid": 3.0, "long": 5.0}
                _style_threshold = min_pnl_for_ai.get(style, 1.5)
                _sl_pct = self.settings.get("stop_loss_pct", 2.5)
                _tp_pct = self.settings.get("take_profit_pct", 6.0)
                # AI 청산은 최소 손절% 이상 수익일 때만 발동 (손익비 보장)
                ai_pnl_threshold = max(_style_threshold, _sl_pct)
                if (
                    pnl_pct >= ai_pnl_threshold
                    and not pos.get("trailing_active")
                    and ai_analyst.is_ai_available()
                    and self.settings.get("ai_exit_assist", True)
                ):
                    sl_gap = (current_price - pos["stop_loss_price"]) / current_price * 100
                    exit_ai = await ai_analyst.check_exit(
                        symbol=symbol,
                        pnl_pct=pnl_pct,
                        strategy_type=pos.get("strategy_type", "standard"),
                        signals=pos.get("signals", []),
                        sl_gap_pct=sl_gap,
                        sl_pct=_sl_pct,
                        tp_pct=_tp_pct,
                    )
                    if exit_ai["action"] == "close_now":
                        log_entry = {
                            "at": datetime.now(KST).strftime("%Y-%m-%d %H:%M KST"),
                            "type": "exit_action",
                            "symbol": symbol,
                            "action": "close_now",
                            "pnl_pct": pnl_pct,
                            "reason": exit_ai["reason"],
                        }
                        self._analysis_log.insert(0, log_entry)
                        if len(self._analysis_log) > 20:
                            self._analysis_log.pop()
                        await self._close_position(symbol, current_price, "ai_exit")
                        continue
                    elif exit_ai["action"] == "tighten_sl":
                        # SL을 현재가 기준 절반 거리로 상향
                        new_sl = pos["avg_price"] * (1 + (pnl_pct - ai_pnl_threshold / 2) / 100)
                        if new_sl > pos["stop_loss_price"]:
                            pos["stop_loss_price"] = new_sl
                            log_entry = {
                                "at": datetime.now(KST).strftime("%Y-%m-%d %H:%M KST"),
                                "type": "exit_action",
                                "symbol": symbol,
                                "action": "tighten_sl",
                                "pnl_pct": pnl_pct,
                                "reason": exit_ai["reason"],
                            }
                            self._analysis_log.insert(0, log_entry)
                            if len(self._analysis_log) > 20:
                                self._analysis_log.pop()
                            logger.info(f"AutoBot AI SL 상향 {symbol}: {new_sl:,.0f}₩ ({exit_ai['reason']})")

                # ── 자율 판단: 물타기 / 추매 / 피라미딩 ─────────────────────
                # 고정 임계값 대신 현재 신호 강도와 점수로 시점 판단
                scan = next((r for r in (scan_results or []) if r["symbol"] == symbol), None)
                balance = self._broker.balance.get(self._quote_currency, 0)

                if (
                    self.settings["auto_avg_down"]
                    and pos["avg_down_count"] < self.settings["max_avg_down"]
                    and pnl_pct < 0
                    and balance >= 5_000
                    and self._current_regime.get("regime") != "downtrend"  # 하락추세에서 물타기 금지
                    and self._should_avg_down(pos, current_price, scan)
                ):
                    await self._add_to_position(symbol, "avg_down", current_price)

                elif (
                    self.settings["auto_add"]
                    and pos["add_count"] < self.settings["max_add"]
                    and pnl_pct > 0
                    and balance >= 5_000
                    and self._should_add(pos, current_price, scan)
                ):
                    await self._add_to_position(symbol, "add", current_price)

                elif (
                    self.settings.get("pyramid_enabled", False)
                    and pos.get("pyramid_count", 0) < self.settings.get("max_pyramid", 2)
                    and balance >= 5_000
                    and self._should_pyramid(pos, scan)
                ):
                    await self._pyramid_into_position(symbol, current_price)

            except Exception as e:
                logger.warning(f"AutoBot: _check_positions {symbol}: {e}")

    # ── 스캔 결과로 신규 진입 ────────────────────────────────────────────────

    async def _enter_from_scan(self, scan_results: list[dict]):
        """
        스타일 선호 전략을 앞으로 정렬 후 진입.
        3회 이상 거래된 전략이 승률 30% 미만이면 건너뜀.
        TODO 1: AI 진입 확인 → confidence < 65면 스킵, 높으면 포지션 크기 증가.
        """
        try:
            style = self.settings.get("trading_style", "short")
            preferred = STYLE_PREFERRED_STRATEGIES.get(style, [])

            def sort_key(r: dict):
                st = r.get("strategy_type", "standard")
                pref_rank = preferred.index(st) if st in preferred else len(preferred)
                return (pref_rank, -r["score"])

            ordered = sorted(scan_results, key=sort_key)

            # 시장 국면과 무관하게 강세 종목 최대 2개 허용
            OPP_SCORE_THRESHOLD = 75
            opp_entered = 0

            import time as _scan_t
            # 만료된 블랙리스트 항목 정리
            _now = _scan_t.time()
            self._reentry_blacklist = {s: t for s, t in self._reentry_blacklist.items() if t > _now}

            for candidate in ordered:
                if len(self._positions) >= self.settings["max_positions"]:
                    break
                symbol = candidate["symbol"]
                if symbol in self._positions:
                    continue
                # 재진입 금지 체크 (T1: 손절 후 2시간)
                if self._reentry_blacklist.get(symbol, 0) > _scan_t.time():
                    logger.debug(f"AutoBot 재진입 차단 {symbol}: 블랙리스트 잔여 {int(self._reentry_blacklist[symbol] - _scan_t.time())}초")
                    continue

                # ── 급등 오버라이드 감지 ─────────────────────────────────────
                # BTC 흐름과 무관하게 개별 종목 거래량 3배+ & 3봉 가격 3%+ 상승 시
                # regime 스타일·min_score 제약을 완화하고 short 스타일로 즉시 대응
                is_surge = (
                    candidate.get("volume_ratio", 0.0) >= 3.0
                    and candidate.get("price_change_pct", 0.0) >= 3.0
                )

                # ── 평균 회귀 모드 분기 (TODO 25) ────────────────────────────
                strategy_mode = self._current_regime.get("strategy_mode", "momentum")
                if strategy_mode == "mean_reversion" and not is_surge:
                    mr_score = candidate.get("mr_score", 0)
                    if mr_score < 30:
                        continue  # MR 신호 부족 → 스킵
                    # BB 중간선을 TP로, 고정 SL 1.5% 적용
                    bb_mid = candidate.get("bb_mid", 0.0)
                    price  = candidate.get("price", 0.0)
                    if bb_mid > price > 0:
                        candidate = dict(candidate)
                        candidate["tp_pct"]          = round((bb_mid - price) / price * 100, 2)
                        candidate["sl_pct"]          = 1.5
                        candidate["strategy_type"]   = "mean_reversion"
                        candidate["strategy_label"]  = "평균회귀"
                        candidate["signals"]         = candidate.get("mr_signals", []) + candidate.get("signals", [])
                        candidate["score"]           = mr_score

                # ── 멀티 타임프레임 확인 ─────────────────────────────────────
                # 상위봉 bearish 추세 시 min_score +5 (급등 오버라이드 예외)
                mtf_confirmed = candidate.get("mtf_confirmed", True)
                mtf_penalty = 0 if (mtf_confirmed or is_surge) else 10

                if strategy_mode == "mean_reversion" and not is_surge:
                    min_score_for_entry = 30  # MR 모드: mr_score 30 이상이면 진입
                else:
                    min_score_for_entry = (50 if is_surge else self.settings["min_score"]) + mtf_penalty

                is_opportunistic = False
                if candidate["score"] < min_score_for_entry:
                    if (
                        not is_surge
                        and strategy_mode != "mean_reversion"
                        and opp_entered < 2
                        and candidate["score"] >= OPP_SCORE_THRESHOLD
                    ):
                        is_opportunistic = True
                    else:
                        continue

                # 실적 게이팅 (5거래 이상 & 승률 20% 미만일 때만 차단 — 초기 손실로 조기 차단 방지)
                st   = candidate.get("strategy_type", "standard")
                perf = self._strategy_performance.get(st, {})
                total = perf.get("wins", 0) + perf.get("losses", 0)
                if total >= 5 and perf["wins"] / total < 0.20:
                    logger.debug(f"AutoBot: 전략 {st} 승률 낮아 스킵 {symbol}")
                    continue

                # ── 포트폴리오 상관관계 체크 (TODO 10) ──────────────────────
                if self._positions and self._close_cache:
                    corr_ok, corr_reason = self._portfolio_risk.check_correlation(
                        new_symbol=symbol,
                        open_positions=list(self._positions.keys()),
                        close_cache=self._close_cache,
                        threshold=self.settings.get("correlation_threshold", 0.85),
                    )
                    if not corr_ok:
                        logger.info(f"AutoBot 상관관계 차단 {symbol}: {corr_reason}")
                        continue

                # AI 진입 확인 (AI 미설정 또는 기능 OFF 시 바이패스)
                size_multiplier = 1.0
                if ai_analyst.is_ai_available() and self.settings.get("ai_entry_validation", True):
                    ai_result = await ai_analyst.check_entry(
                        symbol=symbol,
                        score=candidate["score"],
                        strategy_type=st,
                        signals=candidate.get("signals", []),
                        rsi=candidate.get("rsi", 50.0),
                    )
                    # 급등 종목은 AI 블록 confidence 기준을 50으로 완화
                    ai_block_threshold = 50 if is_surge else 65
                    if not ai_result["enter"] or ai_result["confidence"] < ai_block_threshold:
                        logger.info(
                            f"AutoBot AI 진입 거부 {symbol}: "
                            f"confidence={ai_result['confidence']} reason={ai_result['reason']}"
                        )
                        log_entry = {
                            "at": datetime.now(KST).strftime("%Y-%m-%d %H:%M KST"),
                            "type": "entry_blocked",
                            "symbol": symbol,
                            "confidence": ai_result["confidence"],
                            "reason": ai_result["reason"],
                        }
                        self._analysis_log.insert(0, log_entry)
                        if len(self._analysis_log) > 20:
                            self._analysis_log.pop()
                        continue
                    size_multiplier = ai_result["size_multiplier"]

                # 포지션 스타일 결정
                if is_surge:
                    # 급등 종목: short 스타일 고정 (빠른 익절 대응)
                    position_style = "short"
                    logger.info(
                        f"AutoBot 급등 오버라이드 진입 {symbol}: "
                        f"vol={candidate.get('volume_ratio', 0):.1f}x  "
                        f"change={candidate.get('price_change_pct', 0):+.1f}%  "
                        f"score={candidate['score']}  style→short"
                    )
                    log_entry = {
                        "at":               datetime.now(KST).strftime("%Y-%m-%d %H:%M KST"),
                        "type":             "surge_override",
                        "symbol":           symbol,
                        "volume_ratio":     candidate.get("volume_ratio", 0),
                        "price_change_pct": candidate.get("price_change_pct", 0),
                        "score":            candidate["score"],
                    }
                    self._analysis_log.insert(0, log_entry)
                    if len(self._analysis_log) > 20:
                        self._analysis_log.pop()
                else:
                    # 규칙 기반 종목별 스타일 결정 → AI 있으면 AI가 덮어씀
                    position_style = self._choose_style_rules(candidate)
                    if ai_analyst.is_ai_available() and self.settings.get("ai_entry_validation", True):
                        style_result = await ai_analyst.choose_position_style(
                            symbol=symbol,
                            strategy_type=candidate.get("strategy_type", "standard"),
                            rsi=candidate.get("rsi", 50.0),
                            score=candidate["score"],
                            signals=candidate.get("signals", []),
                            global_style=style,
                        )
                        position_style = style_result["style"]

                await self._open_position(symbol, candidate, size_multiplier=size_multiplier, position_style=position_style)
                if is_opportunistic:
                    opp_entered += 1
                    log_entry = {
                        "at":     datetime.now(KST).strftime("%Y-%m-%d %H:%M KST"),
                        "type":   "opportunistic_entry",
                        "symbol": symbol,
                        "score":  candidate["score"],
                        "style":  position_style,
                        "reason": f"시장 국면 무관 개별 강세 (score={candidate['score']}, regime={self._current_regime.get('regime')})",
                    }
                    self._analysis_log.insert(0, log_entry)
                    if len(self._analysis_log) > 20:
                        self._analysis_log.pop()
                    logger.info(
                        f"AutoBot 기회 진입 {symbol}: score={candidate['score']} "
                        f"style={position_style} regime={self._current_regime.get('regime')} "
                        f"(시장 무관 개별 강세, opp {opp_entered}/2)"
                    )
                await asyncio.sleep(0.3)
        except Exception as e:
            logger.error(f"AutoBot: enter_from_scan error: {e}", exc_info=True)

    async def _enter_scalping_positions(self, scan_results: list[dict]):
        """
        5m 전용 초단타 병렬 진입.
        글로벌 스타일·시장 국면과 무관하게 5m 강세 종목 최대 2개 scalping으로 진입.
        기존 포지션 슬롯(max_positions) 내에서 동작.
        """
        SCALPING_MIN_SCORE = TRADING_STYLE_PRESETS["scalping"]["min_score"]  # 55
        MAX_SCALPING = 2
        entered = 0
        import time as _sc_t
        try:
            for candidate in sorted(scan_results, key=lambda r: -r["score"]):
                if len(self._positions) >= self.settings["max_positions"]:
                    break
                if entered >= MAX_SCALPING:
                    break
                symbol = candidate["symbol"]
                if symbol in self._positions:
                    continue
                # T1: 재진입 금지 체크 (손절 후 2시간 블랙리스트)
                if self._reentry_blacklist.get(symbol, 0) > _sc_t.time():
                    continue
                if candidate["score"] < SCALPING_MIN_SCORE:
                    break  # 내림차순 정렬이므로 이후도 기준 미달

                # 상관관계 체크
                if self._positions and self._close_cache:
                    corr_ok, corr_reason = self._portfolio_risk.check_correlation(
                        new_symbol=symbol,
                        open_positions=list(self._positions.keys()),
                        close_cache=self._close_cache,
                        threshold=self.settings.get("correlation_threshold", 0.85),
                    )
                    if not corr_ok:
                        logger.info(f"AutoBot 초단타 상관관계 차단 {symbol}: {corr_reason}")
                        continue

                # AI 진입 확인
                size_multiplier = 1.0
                if ai_analyst.is_ai_available() and self.settings.get("ai_entry_validation", True):
                    ai_result = await ai_analyst.check_entry(
                        symbol=symbol,
                        score=candidate["score"],
                        strategy_type=candidate.get("strategy_type", "standard"),
                        signals=candidate.get("signals", []),
                        rsi=candidate.get("rsi", 50.0),
                    )
                    if not ai_result["enter"] or ai_result["confidence"] < 55:
                        logger.info(
                            f"AutoBot 초단타 AI 거부 {symbol}: "
                            f"confidence={ai_result['confidence']} reason={ai_result['reason']}"
                        )
                        continue
                    size_multiplier = ai_result["size_multiplier"]

                await self._open_position(symbol, candidate, size_multiplier=size_multiplier, position_style="scalping")
                entered += 1
                log_entry = {
                    "at":     datetime.now(KST).strftime("%Y-%m-%d %H:%M KST"),
                    "type":   "scalping_parallel",
                    "symbol": symbol,
                    "score":  candidate["score"],
                    "reason": f"5m 병렬 스캔 초단타 진입 (score={candidate['score']}, {entered}/{MAX_SCALPING})",
                }
                self._analysis_log.insert(0, log_entry)
                if len(self._analysis_log) > 20:
                    self._analysis_log.pop()
                logger.info(
                    f"AutoBot 초단타 병렬진입 {symbol}: score={candidate['score']} "
                    f"strategy={candidate.get('strategy_type')} ({entered}/{MAX_SCALPING})"
                )
                await asyncio.sleep(0.3)
        except Exception as e:
            logger.error(f"AutoBot: _enter_scalping_positions error: {e}", exc_info=True)

    def _choose_style_rules(self, candidate: dict) -> str:
        """
        종목별 규칙 기반 최적 매매 스타일 선택 (AI 없이도 동적 결정).
        글로벌 스타일을 기본으로 하되, 해당 코인 신호에 따라 조정.
        """
        rsi     = candidate.get("rsi", 50.0)
        signals = candidate.get("signals", [])
        score   = candidate.get("score", 0)
        global_style = self.settings.get("trading_style", "short")

        # 과열/과매도 → scalping (단기 반전 狙い)
        if rsi > 75 or rsi < 28:
            return "scalping"

        # 강한 모멘텀 복합 신호 + 높은 점수 → mid (추세 추종)
        strong_kw = ("MACD 골든크로스", "거래량 급증", "골든크로스", "강한 상승추세")
        strong_count = sum(1 for s in signals if any(kw in s for kw in strong_kw))
        if strong_count >= 2 and score >= 70:
            return "mid"

        # 단일 강신호 + 괜찮은 점수 → short (기본 단타)
        if strong_count >= 1 and score >= 60:
            return "short"

        # 약한 신호 → 글로벌 스타일 유지
        return global_style

    # ── 최초 진입 ────────────────────────────────────────────────────────────

    async def _open_position(self, symbol: str, scan_result: dict, price: Optional[float] = None, size_multiplier: float = 1.0, position_style: Optional[str] = None):
        if not self._connector:
            return
        try:
            if price is None:
                ticker = await asyncio.wait_for(
                    self._connector.fetch_ticker(symbol), timeout=10
                )
                price = ticker["last"]

            krw = self._broker.balance.get(self._quote_currency, 0)
            total_invested = sum(
                p["avg_price"] * p["total_amount"] for p in self._positions.values()
            )
            total_value = krw + total_invested

            # Kelly Criterion: 최근 30건 거래가 10건 이상이면 Kelly 비중 적용
            recent = self._trade_log[:30]
            kelly_invest = None
            if len(recent) >= 10:
                pnl_list = [t["pnl_pct"] for t in recent]
                wins  = [x for x in pnl_list if x > 0]
                losses = [x for x in pnl_list if x <= 0]
                if wins and losses:
                    wr = len(wins) / len(pnl_list)
                    aw = sum(wins)  / len(wins)  / 100
                    al = abs(sum(losses) / len(losses)) / 100
                    kelly = calc_kelly_fraction(wr, aw, al)
                    if kelly > 0:
                        kelly_invest = total_value * kelly * min(size_multiplier, 1.3)

            # DB 전략에 position_size_pct가 있으면 우선 사용, 없으면 글로벌 설정
            strategy_size_pct = scan_result.get("position_size_pct") or self.settings["position_size_pct"]
            invest_krw = kelly_invest if kelly_invest else krw * strategy_size_pct / 100 * min(size_multiplier, 1.3)
            invest_krw = min(invest_krw, krw * 0.95)  # 잔고 95% 초과 금지

            min_invest = 5_000 if self._quote_currency == "KRW" else 5
            if invest_krw < min_invest:
                logger.warning(f"AutoBot: {self._quote_currency} 부족 ({krw:,.0f}), 진입 불가")
                return

            # ── 포트폴리오 리스크 체크 (일일 손실 한도 / 최대 노출) ──────
            # total_invested_krw에 진입 예정 금액 포함 → 진입 후 예상 노출로 체크
            ok, reason = self._portfolio_risk.can_enter(
                total_value_krw=total_value,
                total_invested_krw=total_invested + invest_krw,
                max_daily_loss_pct=self.settings.get("max_daily_loss_pct", 5.0),
                max_exposure_pct=self.settings.get("max_portfolio_exposure_pct", 80.0),
            )
            if not ok:
                logger.info(f"AutoBot: 진입 차단 [{symbol}] — {reason}")
                return

            amount = invest_krw / price
            entry_order = self._broker.execute_market_order(symbol, "buy", amount, price)

            # 전략별 손절/익절 (스캐너가 분류한 값 우선, 없으면 글로벌 설정)
            sl_pct = scan_result.get("sl_pct") or self.settings["stop_loss_pct"]
            tp_pct = scan_result.get("tp_pct") or self.settings["take_profit_pct"]
            sl = price * (1 - sl_pct / 100)
            tp = price * (1 + tp_pct / 100)
            now = datetime.now(KST).isoformat()

            # 포지션별 매매 스타일 (AI 선택 or 글로벌)
            pos_style = position_style or self.settings.get("trading_style", "short")
            pos_preset = TRADING_STYLE_PRESETS.get(pos_style, TRADING_STYLE_PRESETS["short"])

            self._positions[symbol] = {
                "symbol": symbol,
                # 다중 진입 지원
                "entries": [{"price": price, "amount": amount, "at": now, "type": "initial"}],
                "avg_price": price,
                "total_amount": amount,
                # 리스크
                "stop_loss_price": sl,
                "take_profit_price": tp,
                # 실시간
                "current_price": price,
                "unrealized_pnl_pct": 0.0,
                "unrealized_pnl_krw": 0,
                # 포지션별 트레일링 스탑 파라미터
                "highest_price": price,
                "trailing_active": False,
                "trailing_activate_pct": pos_preset["trailing_activate_pct"],
                "trailing_pct":          pos_preset["trailing_pct"],
                # 포지션별 매매 스타일 & 투자 성향
                "position_style":       pos_style,
                "position_style_label": pos_preset["label"],
                "risk_profile":         self.settings.get("risk_profile", "balanced"),
                # 메타
                "entry_at": now,
                "score": scan_result.get("score", 0),
                "signals": scan_result.get("signals", []),
                "strategy_type": scan_result.get("strategy_type", "standard"),
                "strategy_label": scan_result.get("strategy_label", "표준"),
                # 카운터
                "avg_down_count": 0,
                "add_count": 0,
                "pyramid_count": 0,
                # 수수료 누적 (진입 수수료 → 청산 시 순손익 계산에 사용)
                "total_fee_krw": entry_order.get("fee", 0),
            }
            logger.info(f"AutoBot: 진입 {symbol} @ {price:,.0f} ₩  수량={amount:.6f}  점수={scan_result.get('score',0)}")
        except Exception as e:
            logger.error(f"AutoBot: 진입 실패 {symbol}: {e}")

    # ── 자율 판단: 물타기 / 추매 / 피라미딩 ─────────────────────────────────

    def _should_avg_down(self, pos: dict, current_price: float, scan: dict | None) -> bool:
        """
        물타기 자율 판단.
        스캔 결과의 신호 강도에 따라 임계값을 동적으로 조정:
        - 반등 신호 강함 + 점수 유효 → 임계값 50% 완화 (더 일찍 진입)
        - 점수 붕괴 (min_score * 0.6 미만) → 차단 (추세 붕괴 방어)
        - 스캔 없음 → 설정 임계값 그대로 적용
        물타기 임계값은 해당 포지션 SL보다 좁아야 발동 가능:
        - pos의 SL이 avg_down_threshold보다 좁으면 threshold를 SL * 0.7로 제한
        """
        avg = pos["avg_price"]
        drop_pct = (avg - current_price) / avg * 100
        threshold = self.settings["avg_down_threshold_pct"]

        # SL보다 넓은 threshold는 손절 후에야 발동 → SL * 0.7로 자동 제한
        sl_price = pos.get("stop_loss_price", 0)
        if sl_price > 0 and avg > 0:
            sl_pct = (avg - sl_price) / avg * 100
            if threshold >= sl_pct:
                threshold = round(sl_pct * 0.7, 2)

        if scan is None:
            return drop_pct >= threshold

        score = scan["score"]
        signals = scan.get("signals", [])
        min_score = self.settings["min_score"]

        # 점수 붕괴: 추세가 무너진 것으로 판단 → 물타기 차단
        if score < min_score * 0.6:
            return False

        # 반등 신호 감지
        reversal_kw = ("과매도", "반등", "골든크로스", "BB 하단")
        has_reversal = any(any(kw in s for kw in reversal_kw) for s in signals)

        if has_reversal and score >= min_score:
            # 강한 반등 신호 → 임계값 절반만 내려와도 실행
            return drop_pct >= threshold * 0.5

        # 점수 살아있음 → 기본 임계값 유지
        return drop_pct >= threshold and score >= min_score * 0.8

    def _should_add(self, pos: dict, current_price: float, scan: dict | None) -> bool:
        """
        추매 자율 판단.
        - 강한 모멘텀 신호 → 임계값 50% 완화 (더 일찍 추가 매수)
        - 신호 약하면 기본 임계값 적용
        """
        avg = pos["avg_price"]
        rise_pct = (current_price - avg) / avg * 100
        threshold = self.settings["add_threshold_pct"]

        if scan is None:
            return rise_pct >= threshold

        score = scan["score"]
        signals = scan.get("signals", [])
        min_score = self.settings["min_score"]

        momentum_kw = ("MACD 골든크로스", "거래량 급증", "골든크로스", "상승추세")
        has_momentum = any(any(kw in s for kw in momentum_kw) for s in signals)

        if has_momentum and score >= min_score + 5:
            # 강한 모멘텀 → 임계값 절반만 올라와도 추매
            return rise_pct >= threshold * 0.5

        return rise_pct >= threshold and score >= min_score

    def _should_pyramid(self, pos: dict, scan: dict | None) -> bool:
        """
        피라미딩 자율 판단.
        - 강한 신호 → 수익률 임계값 70%에서 진입 허용
        - 매우 강한 신호(MACD·거래량 복합) → 더 적극적으로
        """
        pnl_pct = pos.get("unrealized_pnl_pct", 0.0)
        threshold = self.settings.get("pyramid_threshold_pct", 3.0)

        if scan is None:
            return pnl_pct >= threshold

        score = scan["score"]
        signals = scan.get("signals", [])
        min_score = self.settings["min_score"]

        strong_kw = ("MACD 골든크로스", "거래량 급증", "골든크로스")
        strong_count = sum(1 for s in signals if any(kw in s for kw in strong_kw))

        if strong_count >= 2 and score >= min_score + 10:
            # 복합 강신호 → 임계값 60%에서 피라미딩
            return pnl_pct >= threshold * 0.6
        if strong_count >= 1 and score >= min_score + 5:
            # 단일 강신호 → 임계값 80%에서 피라미딩
            return pnl_pct >= threshold * 0.8

        return pnl_pct >= threshold and score >= min_score

    # ── 추가 매수 (물타기 / 추매) ────────────────────────────────────────────

    async def _add_to_position(self, symbol: str, mode: str, price: float):
        """
        mode: "avg_down" (물타기) | "add" (추매)
        물타기 = 초기 사이즈의 50%, 추매 = 25%
        """
        pos = self._positions.get(symbol)
        if pos is None:
            return
        try:
            krw = self._broker.balance.get(self._quote_currency, 0)
            ratio = 0.5 if mode == "avg_down" else 0.25
            invest_krw = krw * self.settings["position_size_pct"] / 100 * ratio
            invest_krw = min(invest_krw, krw * 0.5)  # 잔고 50% 초과 금지

            min_invest = 5_000 if self._quote_currency == "KRW" else 5
            if invest_krw < min_invest:
                return

            amount = invest_krw / price
            add_order = self._broker.execute_market_order(symbol, "buy", amount, price)
            pos["total_fee_krw"] = pos.get("total_fee_krw", 0) + add_order.get("fee", 0)

            # 평단가 재계산
            total_cost = pos["avg_price"] * pos["total_amount"] + price * amount
            pos["total_amount"] += amount
            pos["avg_price"] = total_cost / pos["total_amount"]

            now = datetime.now(KST).isoformat()
            pos["entries"].append({"price": price, "amount": amount, "at": now, "type": mode})

            if mode == "avg_down":
                pos["avg_down_count"] += 1
                # 전략별 SL/TP 우선, 없으면 글로벌 설정 — 새 평단 기준으로 재설정
                avg = pos["avg_price"]
                st_cfg = STRATEGY_CONFIGS.get(pos.get("strategy_type", "standard"), {})
                sl_pct = st_cfg.get("sl_pct") or self.settings["stop_loss_pct"]
                tp_pct = st_cfg.get("tp_pct") or self.settings["take_profit_pct"]
                pos["stop_loss_price"] = avg * (1 - sl_pct / 100)
                pos["take_profit_price"] = avg * (1 + tp_pct / 100)
            else:
                pos["add_count"] += 1

            logger.info(
                f"AutoBot: {mode} {symbol} @ {price:,.0f} ₩  "
                f"새 평단={pos['avg_price']:,.0f}  총수량={pos['total_amount']:.6f}"
            )
        except Exception as e:
            logger.error(f"AutoBot: {mode} 실패 {symbol}: {e}")

    # ── 피라미딩 ─────────────────────────────────────────────────────────────

    async def _check_pyramid_entry(self, symbol: str, current_price: float, scan_results: list[dict]):
        """
        피라미딩 진입 조건 확인 후 충족 시 추가 매수.
        조건: pnl_pct >= pyramid_threshold AND 최신 스코어 >= min_score
        """
        pos = self._positions.get(symbol)
        if pos is None:
            return

        pnl_pct = pos.get("unrealized_pnl_pct", 0.0)
        threshold = self.settings.get("pyramid_threshold_pct", 3.0)
        if pnl_pct < threshold:
            return

        # 최신 스캔 결과에서 해당 종목 스코어 확인
        scan = next((r for r in scan_results if r["symbol"] == symbol), None)
        if scan is None or scan["score"] < self.settings["min_score"]:
            return

        await self._pyramid_into_position(symbol, current_price)

    async def _pyramid_into_position(self, symbol: str, price: float):
        """피라미딩: 초기 투자금의 50% 추가 매수 후 평단 재계산 및 SL 재조정."""
        pos = self._positions.get(symbol)
        if pos is None:
            return
        try:
            krw = self._broker.balance.get(self._quote_currency, 0)
            invest_krw = krw * self.settings["position_size_pct"] / 100 * 0.5
            invest_krw = min(invest_krw, krw * 0.5)

            min_invest = 5_000 if self._quote_currency == "KRW" else 5
            if invest_krw < min_invest:
                return

            amount = invest_krw / price
            order = self._broker.execute_market_order(symbol, "buy", amount, price)
            pos["total_fee_krw"] = pos.get("total_fee_krw", 0) + order.get("fee", 0)

            # 평단가 재계산
            total_cost = pos["avg_price"] * pos["total_amount"] + price * amount
            pos["total_amount"] += amount
            pos["avg_price"] = total_cost / pos["total_amount"]

            # SL 새 평단 기준으로 재조정 (TP는 원래 목표 유지)
            avg = pos["avg_price"]
            sl_pct = self.settings["stop_loss_pct"]
            pos["stop_loss_price"] = avg * (1 - sl_pct / 100)

            now = datetime.now(KST).isoformat()
            pos["entries"].append({"price": price, "amount": amount, "at": now, "type": "pyramid"})
            pos["pyramid_count"] = pos.get("pyramid_count", 0) + 1

            logger.info(
                f"AutoBot 피라미딩 {symbol} @ {price:,.0f} ₩  "
                f"새 평단={pos['avg_price']:,.0f}  횟수={pos['pyramid_count']}"
            )
        except Exception as e:
            logger.error(f"AutoBot 피라미딩 실패 {symbol}: {e}")


    # ── 수동 조작 API 진입점 ─────────────────────────────────────────────────

    async def manual_add(self, symbol: str, mode: str) -> dict:
        """수동 추매(add) / 물타기(avg_down)"""
        pos = self._positions.get(symbol)
        if pos is None:
            return {"ok": False, "message": "포지션 없음"}

        limit = self.settings["max_avg_down"] if mode == "avg_down" else self.settings["max_add"]
        count_key = "avg_down_count" if mode == "avg_down" else "add_count"
        if pos[count_key] >= limit:
            return {"ok": False, "message": f"최대 {limit}회 제한 초과"}

        if not self._connector:
            return {"ok": False, "message": "커넥터 없음 (봇 시작 필요)"}

        try:
            ticker = await asyncio.wait_for(self._connector.fetch_ticker(symbol), timeout=10)
            price = ticker["last"]
            await self._add_to_position(symbol, mode, price)
            return {"ok": True, "avg_price": pos["avg_price"], "total_amount": pos["total_amount"]}
        except Exception as e:
            return {"ok": False, "message": str(e)}

    async def manual_close(self, symbol: str) -> dict:
        """수동 청산"""
        if symbol not in self._positions:
            return {"ok": False, "message": "포지션 없음"}
        if not self._connector:
            return {"ok": False, "message": "커넥터 없음"}
        try:
            ticker = await asyncio.wait_for(self._connector.fetch_ticker(symbol), timeout=10)
            await self._close_position(symbol, ticker["last"], "manual")
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "message": str(e)}

    # ── 부분 청산 (TODO 22) ────────────────────────────────────────────────

    async def _check_partial_exit(self, symbol: str, price: float):
        """
        부분 청산 전략 (TODO 22).
        avg→TP 거리의 partial_exit_trigger_pct 도달 시 포지션의
        partial_exit_ratio 만큼 매도 후:
          - SL을 진입가 + 0.5%로 상향 (원금 보호)
          - 트레일링 스탑 즉시 활성화 (나머지 물량으로 추가 수익 추구)
          - partial_exited = True 플래그 → 중복 발동 방지
        """
        if not self.settings.get("partial_exit_enabled"):
            return
        pos = self._positions.get(symbol)
        if pos is None or pos.get("partial_exited"):
            return

        avg = pos["avg_price"]
        tp  = pos["take_profit_price"]

        # TP 상한이 제거된 상태(trailing_active=True)이거나 손실 중이면 스킵
        if tp == float("inf") or tp <= avg or price <= avg:
            return

        trigger_pct   = self.settings.get("partial_exit_trigger_pct", 0.6)
        trigger_price = avg + (tp - avg) * trigger_pct
        if price < trigger_price:
            return

        ratio       = self.settings.get("partial_exit_ratio", 0.4)
        exit_amount = pos["total_amount"] * ratio
        if exit_amount <= 0:
            return

        try:
            exit_order = self._broker.execute_market_order(symbol, "sell", exit_amount, price)
            exit_fee   = exit_order.get("fee", 0)

            # 부분 청산 손익 계산 (진입 수수료도 비례 차감)
            entry_fee_partial = pos.get("total_fee_krw", 0) * ratio
            partial_pnl_krw   = round((price - avg) * exit_amount - entry_fee_partial - exit_fee)
            partial_pnl_pct   = round(partial_pnl_krw / (avg * exit_amount) * 100, 2) if avg > 0 else 0.0

            # 일일 PnL 기록
            self._portfolio_risk.record_trade(partial_pnl_krw)

            # 포지션 잔량·수수료 갱신
            pos["total_amount"]  -= exit_amount
            pos["total_fee_krw"]  = pos.get("total_fee_krw", 0) * (1.0 - ratio)
            pos["partial_exited"] = True

            # SL을 진입가 + 0.5%로 상향 (원금 보호)
            new_sl = avg * 1.005
            if new_sl > pos["stop_loss_price"]:
                pos["stop_loss_price"] = new_sl

            # 트레일링 스탑 즉시 활성화, TP 상한 제거
            pos["trailing_active"]   = True
            pos["highest_price"]     = max(price, pos.get("highest_price", price))
            pos["take_profit_price"] = float("inf")

            # 미실현 손익 재계산
            remaining = pos["total_amount"]
            remaining_invested = avg * remaining
            est_exit_fee = price * remaining * self._broker.fee_rate
            net_pnl = (price - avg) * remaining - pos.get("total_fee_krw", 0) - est_exit_fee
            pos["unrealized_pnl_krw"] = round(net_pnl)
            pos["unrealized_pnl_pct"] = round(net_pnl / remaining_invested * 100, 2) if remaining_invested > 0 else 0.0

            logger.info(
                f"AutoBot 부분 청산 {symbol}: {ratio*100:.0f}% @ {price:,.0f}₩  "
                f"pnl={partial_pnl_pct:+.2f}%  잔량={remaining:.6f}  "
                f"SL↑={new_sl:,.0f}₩ → 트레일링 활성화"
            )
        except Exception as e:
            logger.error(f"AutoBot 부분 청산 실패 {symbol}: {e}")

    # ── 청산 ─────────────────────────────────────────────────────────────────

    async def _close_position(self, symbol: str, price: float, reason: str):
        pos = self._positions.pop(symbol, None)
        if pos is None:
            return
        try:
            amount = pos["total_amount"]
            exit_order = self._broker.execute_market_order(symbol, "sell", amount, price)

            avg = pos["avg_price"]
            # ── 수수료 차감 순손익 계산 ───────────────────────────────────────
            # 진입 수수료(누적) + 청산 수수료 = 왕복 수수료
            entry_fees = pos.get("total_fee_krw", 0)
            exit_fee   = exit_order.get("fee", 0)
            total_fees = entry_fees + exit_fee
            total_invested = avg * amount
            pnl_krw = round((price - avg) * amount - total_fees)
            pnl_pct = round(pnl_krw / total_invested * 100, 2) if total_invested > 0 else 0.0
            exit_at = datetime.now(KST).isoformat()

            # 일일 PnL 추적 (일일 손실 한도 체크용)
            self._portfolio_risk.record_trade(pnl_krw)

            record = {
                "symbol": symbol,
                "avg_price": avg,
                "exit_price": price,
                "total_amount": amount,
                "entries": pos["entries"],
                "pnl_pct": pnl_pct,
                "pnl_krw": pnl_krw,
                "exit_reason": reason,
                "entry_at": pos["entry_at"],
                "exit_at": exit_at,
                "score": pos.get("score", 0),
                "avg_down_count": pos["avg_down_count"],
                "add_count": pos["add_count"],
                "position_style": pos.get("position_style", "short"),
                "position_style_label": pos.get("position_style_label", "단타"),
                "risk_profile": pos.get("risk_profile", "balanced"),
            }
            self._trade_log.insert(0, record)
            if len(self._trade_log) > MAX_TRADE_LOG:
                self._trade_log.pop()

            # 전략 실적 업데이트 (DB 전략 포함 동적 추적)
            st = pos.get("strategy_type", "standard")
            perf = self._strategy_performance.setdefault(
                st, {"wins": 0, "losses": 0, "total_pnl": 0.0}
            )
            if pnl_pct > 0:
                perf["wins"] += 1
            else:
                perf["losses"] += 1
            perf["total_pnl"] = round(perf["total_pnl"] + pnl_pct, 2)

            # TODO 3: 연속 손절 카운터 + AI 자기 분석
            if reason == "stop_loss" and pnl_pct < 0:
                self._consecutive_losses += 1

                # T1: 손절 종목 재진입 금지 2시간
                import time as _cl_t
                self._reentry_blacklist[symbol] = _cl_t.time() + 7200
                logger.info(f"AutoBot 재진입 금지 등록 {symbol}: 2시간")

                # T2: 3연속 손절 → 30분 쿨다운
                if self._consecutive_losses >= 3:
                    self._cooldown_until = _cl_t.time() + 1800
                    logger.warning(
                        f"AutoBot 연속 손절 {self._consecutive_losses}회 → 30분 신규 진입 차단"
                    )
                    log_entry = {
                        "at":     datetime.now(KST).strftime("%Y-%m-%d %H:%M KST"),
                        "type":   "loss_analysis",
                        "issue":  "COOLDOWN",
                        "reason": f"{self._consecutive_losses}연속 손절 — 30분 쿨다운 시작",
                        "adjusted": [],
                    }
                    self._analysis_log.insert(0, log_entry)
                    if len(self._analysis_log) > 20:
                        self._analysis_log.pop()

                if self._consecutive_losses >= 3 and ai_analyst.is_ai_available() and self.settings.get("ai_loss_analysis", True):
                    losing_trades = [t for t in self._trade_log if t.get("pnl_pct", 0) < 0][:5]
                    asyncio.create_task(self._run_loss_analysis(losing_trades))
            else:
                self._consecutive_losses = 0   # 익절/트레일링이면 리셋

            # DB 영속화
            await self._save_trade_to_db(record, pos)

            logger.info(
                f"AutoBot 청산 {symbol} @ {price:,.0f}₩  "
                f"pnl={pnl_pct:+.2f}%  사유={reason}"
            )
        except Exception as e:
            logger.error(f"AutoBot: 청산 실패 {symbol}: {e}")

    # ── 선물 전용 메서드 ─────────────────────────────────────────────────────

    async def _enter_futures_from_scan(self, scan_results: list[dict]):
        """선물 스캔 결과에서 신규 포지션 진입."""
        min_score = self.settings["min_score"]
        candidates = [
            r for r in scan_results
            if r["score"] >= min_score
            and r["symbol"] not in self._futures_positions
        ]
        for candidate in candidates:
            if len(self._futures_positions) >= self.settings["max_positions"]:
                break
            try:
                await self._open_futures_position(candidate)
                await asyncio.sleep(0.3)
            except Exception as e:
                logger.error(f"AutoBot 선물 진입 오류 {candidate['symbol']}: {e}")

    async def _open_futures_position(self, scan_result: dict):
        """선물 포지션 개시 (모의 or 실거래)."""
        symbol   = scan_result["symbol"]
        side     = scan_result.get("side", "long")
        leverage = self.settings["leverage"]

        if symbol in self._futures_positions:
            return

        try:
            price = await asyncio.wait_for(
                self._futures_connector.get_mark_price(symbol), timeout=10
            )
        except Exception as e:
            logger.warning(f"AutoBot 선물: {symbol} 마크가격 조회 실패 ({e})")
            return

        usdt_balance = self._futures_broker.usdt_balance
        sl_pct = scan_result.get("sl_pct") or self.settings["stop_loss_pct"]
        usdt_amount = calc_futures_position_size(
            usdt_balance=usdt_balance,
            leverage=leverage,
            risk_pct=0.02,
            sl_pct=sl_pct / 100,
        )
        if usdt_amount < 5:
            logger.warning(f"AutoBot 선물: USDT 부족 ({usdt_balance:.2f}), 진입 불가")
            return

        try:
            entry_order = self._futures_broker.open_position(
                symbol=symbol,
                side=side,
                usdt_amount=usdt_amount,
                leverage=leverage,
                price=price,
            )
        except ValueError as e:
            logger.warning(f"AutoBot 선물 진입 실패 {symbol}: {e}")
            return

        fp = self._futures_broker.positions[symbol]
        tp_pct = scan_result.get("tp_pct") or self.settings["take_profit_pct"]
        sl_price = price * (1 - sl_pct / 100) if side == "long" else price * (1 + sl_pct / 100)
        tp_price = price * (1 + tp_pct / 100) if side == "long" else price * (1 - tp_pct / 100)

        self._futures_positions[symbol] = {
            "symbol":            symbol,
            "side":              side,
            "entry_price":       price,
            "contracts":         fp["contracts"],
            "leverage":          leverage,
            "margin_mode":       self.settings["margin_mode"],
            "initial_margin":    fp["initial_margin"],
            "liquidation_price": fp["liquidation_price"],
            "stop_loss_price":   sl_price,
            "take_profit_price": tp_price,
            "current_price":     price,
            "unrealized_pnl_usdt": 0.0,
            "unrealized_pnl_pct":  0.0,
            "funding_rate":      scan_result.get("funding_rate", 0.0),
            "score":             scan_result["score"],
            "signals":           scan_result.get("signals", []),
            "strategy_type":     scan_result.get("strategy_type", "standard"),
            "strategy_label":    scan_result.get("strategy_label", "표준"),
            "entry_at":          datetime.now(KST).isoformat(),
        }

        logger.info(
            f"AutoBot 선물 진입 {symbol} {side.upper()} @ {price:.4f} USDT  "
            f"증거금={usdt_amount:.2f}  레버리지={leverage}x  점수={scan_result['score']}"
        )

    async def _close_futures_position(self, symbol: str, price: float, reason: str):
        """선물 포지션 청산."""
        pos = self._futures_positions.pop(symbol, None)
        if pos is None:
            return
        try:
            close_order = self._futures_broker.close_position(symbol, price)
            pnl_usdt = close_order["pnl"]
            entry     = pos["entry_price"]
            invested  = pos["initial_margin"]
            pnl_pct   = round(pnl_usdt / invested * 100, 2) if invested > 0 else 0.0
            exit_at   = datetime.now(KST).isoformat()

            self._portfolio_risk.record_trade(pnl_usdt)
            if reason == "stop_loss" and pnl_pct < 0:
                self._consecutive_losses += 1
            else:
                self._consecutive_losses = 0

            # 전략 실적 업데이트 (현물과 동일하게 추적)
            st = pos.get("strategy_type", "standard")
            perf = self._strategy_performance.setdefault(st, {"wins": 0, "losses": 0, "total_pnl": 0.0})
            if pnl_pct > 0:
                perf["wins"] += 1
            else:
                perf["losses"] += 1
            perf["total_pnl"] = round(perf["total_pnl"] + pnl_pct, 2)

            record = {
                "symbol":       symbol,
                "avg_price":    entry,
                "exit_price":   price,
                "total_amount": pos["contracts"],
                "entries":      [{"price": entry, "amount": pos["contracts"],
                                  "at": pos["entry_at"], "type": "initial"}],
                "pnl_pct":      pnl_pct,
                "pnl_krw":      pnl_usdt,
                "exit_reason":  reason,
                "entry_at":     pos["entry_at"],
                "exit_at":      exit_at,
                "score":        pos.get("score", 0),
                "avg_down_count": 0,
                "add_count":    0,
                "position_style": pos.get("position_style", "short"),
                "position_style_label": pos.get("position_style_label", "단타"),
                "risk_profile": pos.get("risk_profile", "balanced"),
            }
            self._trade_log.insert(0, record)
            if len(self._trade_log) > MAX_TRADE_LOG:
                self._trade_log.pop()

            await self._save_futures_trade_to_db(record, pos)

            logger.info(
                f"AutoBot 선물 청산 {symbol} {pos['side'].upper()} @ {price:.4f} USDT  "
                f"pnl={pnl_pct:+.2f}%  사유={reason}"
            )
        except Exception as e:
            logger.error(f"AutoBot 선물 청산 실패 {symbol}: {e}")

    async def _check_futures_positions(self, scan_results: list[dict]):
        """선물 포지션 SL/TP 체크 + 청산가 모니터링."""
        for symbol, pos in list(self._futures_positions.items()):
            price = pos.get("current_price", pos["entry_price"])
            if not price:
                continue

            self._futures_broker.update_unrealized_pnl(symbol, price)
            fp = self._futures_broker.positions.get(symbol)
            if fp:
                invested = pos["initial_margin"]
                pos["unrealized_pnl_usdt"] = round(fp["unrealized_pnl"], 4)
                pos["unrealized_pnl_pct"]  = round(
                    fp["unrealized_pnl"] / invested * 100, 2
                ) if invested > 0 else 0.0

            side = pos["side"]
            sl   = pos["stop_loss_price"]
            tp   = pos["take_profit_price"]

            # SL/TP 체크
            if side == "long":
                if price <= sl:
                    await self._close_futures_position(symbol, price, "stop_loss")
                    continue
                if price >= tp:
                    await self._close_futures_position(symbol, price, "take_profit")
                    continue
            else:  # short
                if price >= sl:
                    await self._close_futures_position(symbol, price, "stop_loss")
                    continue
                if price <= tp:
                    await self._close_futures_position(symbol, price, "take_profit")
                    continue

            # 청산가 5% 이내 접근 → 강제 청산
            liq = pos.get("liquidation_price")
            if liq and liq > 0:
                distance_pct = abs(price - liq) / price * 100
                if distance_pct < 5.0:
                    logger.warning(
                        f"[청산가 경고] {symbol} 청산가 {liq:.4f}까지 {distance_pct:.1f}% — 강제 청산"
                    )
                    await self._close_futures_position(symbol, price, "liquidation_warning")

    async def _check_funding_rates(self):
        """선물 포지션의 펀딩비 부과 및 로그 기록."""
        if not self._futures_connector:
            return
        for symbol, pos in list(self._futures_positions.items()):
            try:
                rate = await asyncio.wait_for(
                    self._futures_connector.get_funding_rate(symbol), timeout=5
                )
                pos["funding_rate"] = rate
                self._futures_broker.apply_funding(symbol, rate)
                if abs(rate) > 0.0005:
                    logger.info(
                        f"[펀딩비] {symbol} {rate * 100:.4f}%  "
                        f"({pos['side']}) — 포지션 방향 재검토 권장"
                    )
            except Exception:
                pass

    async def _save_futures_trade_to_db(self, record: dict, pos: dict):
        """선물 거래 내역 DB 저장."""
        try:
            from ..core.database import AsyncSessionLocal
            from ..models.auto_bot_trade import AutoBotTrade
            async with AsyncSessionLocal() as session:
                session.add(AutoBotTrade(
                    symbol=record["symbol"],
                    avg_price=record["avg_price"],
                    exit_price=record["exit_price"],
                    total_amount=record["total_amount"],
                    entries=record["entries"],
                    pnl_pct=record["pnl_pct"],
                    pnl_krw=record["pnl_krw"],
                    exit_reason=record["exit_reason"],
                    strategy_type=pos.get("strategy_type", "standard"),
                    strategy_label=pos.get("strategy_label", "표준"),
                    position_style=pos.get("position_style", "short"),
                    position_style_label=pos.get("position_style_label", "단타"),
                    risk_profile=pos.get("risk_profile", "balanced"),
                    score=pos.get("score", 0),
                    avg_down_count=0,
                    add_count=0,
                    entry_at=record["entry_at"],
                    exit_at=record["exit_at"],
                    is_paper=True,
                    market_type="futures",
                    side=pos.get("side", "long"),
                    leverage=pos.get("leverage", 1),
                    margin_mode=pos.get("margin_mode", "cross"),
                    liquidation_price=pos.get("liquidation_price"),
                    funding_paid=self._futures_broker.positions.get(
                        record["symbol"], {}
                    ).get("funding_paid", 0.0),
                ))
                await session.commit()
        except Exception as e:
            logger.error(f"AutoBot 선물: DB 저장 실패 {record['symbol']}: {e}", exc_info=True)

    async def _run_loss_analysis(self, losing_trades: list[dict]):
        """TODO 3: 연속 손절 3회 → AI 원인 분석 → 파라미터 자동 조정"""
        try:
            result = await ai_analyst.analyze_losses(losing_trades, self.settings)
            now_str = datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")

            # 파라미터 조정
            adjusted = []
            if result["sl_pct_delta"] > 0:
                new_sl = round(self.settings["stop_loss_pct"] + result["sl_pct_delta"], 1)
                self.settings["stop_loss_pct"] = new_sl
                adjusted.append(f"SL→{new_sl}%")
            if result["min_score_delta"] > 0:
                new_score = min(72, self.settings["min_score"] + result["min_score_delta"])
                self.settings["min_score"] = new_score
                adjusted.append(f"최소점수→{new_score}")

            self._consecutive_losses = 0   # 리셋

            log_entry = {
                "at":       now_str,
                "type":     "loss_analysis",
                "issue":    result["issue"],
                "reason":   result["reason"],
                "adjusted": adjusted,
            }
            self._analysis_log.insert(0, log_entry)
            if len(self._analysis_log) > 20:
                self._analysis_log.pop()

            logger.info(
                f"AutoBot AI 손절 분석 완료: issue={result['issue']} "
                f"조정={adjusted} ({result['reason']})"
            )
        except Exception as e:
            logger.debug(f"AutoBot 손절 분석 오류: {e}")

    async def _run_performance_feedback(self):
        """
        30분마다 최근 거래 실적(승률·실효 R:R)을 측정해 min_score 자동 보정.

        연속 손절이 아닌 산발적 손절 패턴(손-익-손-익-손)에도 대응.
        - 승률 < 35% + 실효R:R < 1.5 → min_score +3 (진입 기준 강화, 상한 72)
        - 승률 < 35%                   → min_score +2 (상한 72)
        - 승률 > 55% + 실효R:R > 2.0  → min_score -2 (기회 확대, 하한 55)
        """
        import time
        if time.time() - self._last_perf_feedback_at < 1800:
            return
        self._last_perf_feedback_at = time.time()

        recent = self._trade_log[:15]
        if len(recent) < 5:
            return

        wins   = [t for t in recent if t["pnl_pct"] > 0]
        losses = [t for t in recent if t["pnl_pct"] <= 0]
        win_rate  = len(wins) / len(recent)
        avg_win   = sum(t["pnl_pct"] for t in wins)   / len(wins)   if wins   else 0.0
        avg_loss  = abs(sum(t["pnl_pct"] for t in losses) / len(losses)) if losses else 0.0
        actual_rr = round(avg_win / avg_loss, 2) if avg_loss > 0 else 99.0

        cur_score = self.settings["min_score"]
        new_score = cur_score

        if win_rate < 0.35 and actual_rr < 1.5:
            new_score = min(72, cur_score + 3)
        elif win_rate < 0.35:
            new_score = min(72, cur_score + 2)
        elif win_rate > 0.55 and actual_rr > 2.0:
            new_score = max(55, cur_score - 2)

        if new_score == cur_score:
            return

        self.settings["min_score"] = new_score
        direction = "강화" if new_score > cur_score else "완화"
        log_entry = {
            "at":        datetime.now(KST).strftime("%Y-%m-%d %H:%M KST"),
            "type":      "performance_feedback",
            "win_rate":  round(win_rate * 100, 1),
            "actual_rr": actual_rr,
            "n_trades":  len(recent),
            "changed":   [f"min_score {cur_score}→{new_score} (진입기준 {direction})"],
        }
        self._analysis_log.insert(0, log_entry)
        if len(self._analysis_log) > 20:
            self._analysis_log.pop()
        logger.info(
            f"AutoBot 성과 피드백: 승률={win_rate:.0%} 실효R:R={actual_rr:.2f} "
            f"→ min_score {cur_score}→{new_score}"
        )

    async def _save_trade_to_db(self, record: dict, pos: dict):
        try:
            from ..core.database import AsyncSessionLocal
            from ..models.auto_bot_trade import AutoBotTrade
            async with AsyncSessionLocal() as session:
                session.add(AutoBotTrade(
                    symbol=record["symbol"],
                    avg_price=record["avg_price"],
                    exit_price=record["exit_price"],
                    total_amount=record["total_amount"],
                    entries=record["entries"],
                    pnl_pct=record["pnl_pct"],
                    pnl_krw=record["pnl_krw"],
                    exit_reason=record["exit_reason"],
                    strategy_type=pos.get("strategy_type", "standard"),
                    strategy_label=pos.get("strategy_label", "표준"),
                    position_style=pos.get("position_style", "short"),
                    position_style_label=pos.get("position_style_label", "단타"),
                    risk_profile=pos.get("risk_profile", "balanced"),
                    score=pos.get("score", 0),
                    avg_down_count=record["avg_down_count"],
                    add_count=record["add_count"],
                    entry_at=record["entry_at"],
                    exit_at=record["exit_at"],
                    is_paper=True,
                ))
                await session.commit()
        except Exception as e:
            logger.error(f"AutoBot: DB 저장 실패 {record['symbol']}: {e}", exc_info=True)

    # ── 상태 반환 ────────────────────────────────────────────────────────────

    def get_status(self) -> dict:
        # ── 선물 모드 분기 ────────────────────────────────────────────────────
        if self._is_futures:
            return self._get_futures_status()
        # ── 현물 모드 ─────────────────────────────────────────────────────────
        krw = self._broker.balance.get(self._quote_currency, 0)
        positions = list(self._positions.values())

        coin_value = sum(
            p["total_amount"] * p.get("current_price", p["avg_price"])
            for p in positions
        )
        total_value = krw + coin_value

        # 종합 미실현 손익
        total_invested = sum(p["avg_price"] * p["total_amount"] for p in positions)
        unrealized_pnl_krw = sum(p.get("unrealized_pnl_krw", 0) for p in positions)
        unrealized_pnl_pct = round(
            unrealized_pnl_krw / total_invested * 100, 2
        ) if total_invested > 0 else 0.0

        logs = self._trade_log
        avg_pnl = sum(t["pnl_pct"] for t in logs) / len(logs) if logs else 0.0
        realized_pnl_krw = sum(t.get("pnl_krw", 0) for t in logs)

        style = self.settings.get("trading_style", "short")
        style_preset = TRADING_STYLE_PRESETS.get(style, {})

        # 전략별 승률 요약
        strategy_stats = {}
        for st, perf in self._strategy_performance.items():
            total = perf["wins"] + perf["losses"]
            strategy_stats[st] = {
                "wins":      perf["wins"],
                "losses":    perf["losses"],
                "total":     total,
                "win_rate":  round(perf["wins"] / total * 100, 1) if total > 0 else None,
                "total_pnl": perf["total_pnl"],
            }

        # ── 성과 지표 계산 ────────────────────────────────────────────────
        performance = calc_performance(logs)

        # 포지션에 트레일링 스탑 상태 보강
        for p in positions:
            if p.get("trailing_active") and p.get("highest_price"):
                t_pct = p.get("trailing_pct", self.settings["trailing_pct"])
                p["trailing_stop_price"] = round(
                    p["highest_price"] * (1 - t_pct / 100)
                )
            else:
                p["trailing_stop_price"] = None

        return {
            "running": self._running,
            "paused": self._paused,
            "scan_in_progress": self._scan_in_progress,
            "positions": positions,
            "trade_log": logs[:20],
            "scan_results": self._scan_results[:10],
            "last_scan_at": self._last_scan_at,
            "balance_krw": round(krw),
            "fee_rate": self._broker.fee_rate,
            "total_value_krw": round(total_value),
            "unrealized_pnl_krw": round(unrealized_pnl_krw),
            "unrealized_pnl_pct": unrealized_pnl_pct,
            "realized_pnl_krw": round(realized_pnl_krw),
            "avg_pnl_pct": round(avg_pnl, 2),
            "total_trades": len(logs),
            "settings": self.settings,
            "style_label": style_preset.get("label", "단타"),
            "started_at": self._started_at.isoformat() if self._started_at else None,
            "strategy_stats": strategy_stats,
            "preferred_strategies": STYLE_PREFERRED_STRATEGIES.get(style, []),
            # AI 기능 상태
            "ai_available":       ai_analyst.is_ai_available(),
            "ai_regime":          self._current_regime,
            "ai_consecutive_losses": self._consecutive_losses,
            "ai_analysis_log":    self._analysis_log[:10],
            # 성과 지표 (Sharpe / Sortino / MDD / Expectancy 등)
            "performance":        performance,
            # 포트폴리오 리스크 현황
            "daily_pnl_krw":      round(self._portfolio_risk.daily_pnl_krw),
        }

    def _get_futures_status(self) -> dict:
        """선물 모드 상태 반환."""
        usdt = self._futures_broker.usdt_balance
        positions = list(self._futures_positions.values())
        logs = self._trade_log
        style = self.settings.get("trading_style", "short")
        style_preset = TRADING_STYLE_PRESETS.get(style, {})

        total_margin = sum(p["initial_margin"] for p in positions)
        total_unrealized = sum(p.get("unrealized_pnl_usdt", 0) for p in positions)
        total_value = usdt + total_margin + total_unrealized
        avg_pnl = sum(t["pnl_pct"] for t in logs) / len(logs) if logs else 0.0
        realized_pnl = sum(t.get("pnl_krw", 0) for t in logs)  # pnl_krw 필드에 USDT PnL 저장

        performance = calc_performance(logs)

        strategy_stats = {}
        for st, perf in self._strategy_performance.items():
            total = perf["wins"] + perf["losses"]
            strategy_stats[st] = {
                "wins":      perf["wins"],
                "losses":    perf["losses"],
                "total":     total,
                "win_rate":  round(perf["wins"] / total * 100, 1) if total > 0 else None,
                "total_pnl": perf["total_pnl"],
            }

        return {
            "running": self._running,
            "paused":  self._paused,
            "scan_in_progress": self._scan_in_progress,
            "positions": [],                 # 현물 포지션 (선물 모드에서는 항상 비어있음)
            "futures_positions": positions,  # 선물 포지션
            "trade_log": logs[:20],
            "scan_results": self._scan_results[:10],
            "last_scan_at": self._last_scan_at,
            "balance_krw": round(usdt, 4),   # USDT 잔고
            "fee_rate": FUTURES_FEE_RATE,
            "total_value_krw": round(total_value, 4),
            "unrealized_pnl_krw": round(total_unrealized, 4),
            "unrealized_pnl_pct": round(
                total_unrealized / total_margin * 100, 2
            ) if total_margin > 0 else 0.0,
            "realized_pnl_krw": round(realized_pnl, 4),
            "avg_pnl_pct": round(avg_pnl, 2),
            "total_trades": len(logs),
            "settings": self.settings,
            "style_label": style_preset.get("label", "단타"),
            "started_at": self._started_at.isoformat() if self._started_at else None,
            "strategy_stats": strategy_stats,
            "preferred_strategies": STYLE_PREFERRED_STRATEGIES.get(style, []),
            "ai_available":       ai_analyst.is_ai_available(),
            "ai_regime":          self._current_regime,
            "ai_consecutive_losses": self._consecutive_losses,
            "ai_analysis_log":    self._analysis_log[:10],
            "performance":        performance,
            "daily_pnl_krw":      round(self._portfolio_risk.daily_pnl_krw, 4),
            # 선물 전용 추가 정보
            "market_type": "futures",
            "leverage":    self.settings["leverage"],
            "margin_mode": self.settings["margin_mode"],
        }


# ── 싱글턴 ──────────────────────────────────────────────────────────────────

_bot: Optional[AutoTradeBot] = None


def get_auto_bot() -> AutoTradeBot:
    global _bot
    if _bot is None:
        _bot = AutoTradeBot()
    return _bot
