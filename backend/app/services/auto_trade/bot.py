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

from ..exchange.connector import ExchangeConnector, PaperBroker
from .scanner import scan_market, STRATEGY_CONFIGS, STRATEGY_STYLE_CONFIGS, TIMEFRAME_MINUTES
from . import ai_analyst

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
        "timeframe": "1h",
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
        self._connector: Optional[ExchangeConnector] = None
        self._broker = PaperBroker(initial_balance=0, fee_rate=0.0005)
        self._broker.balance = {"KRW": 1_000_000}
        self._price_task: Optional[asyncio.Task] = None
        self._started_at: Optional[datetime] = None

        # 전략별 실적 추적 (wins/losses/total_pnl)
        self._strategy_performance: dict[str, dict] = {
            k: {"wins": 0, "losses": 0, "total_pnl": 0.0}
            for k in ["oversold_bounce", "golden_cross", "macd_momentum", "volume_breakout", "standard"]
        }

        # AI 기능 상태
        self._consecutive_losses: int = 0          # 연속 손절 카운터
        self._last_regime_at: float = 0.0          # 마지막 국면 감지 시각 (epoch)
        self._current_regime: dict = {             # 현재 시장 국면
            "regime": "ranging", "style": "short",
            "min_score_delta": 0, "reason": "초기화"
        }
        self._analysis_log: list[dict] = []        # AI 분석 기록 (최대 20건)

        self.settings: dict = {
            "trading_style": "short",
            "scan_interval_min": 5,
            "max_positions": 4,
            "position_size_pct": 25.0,
            "stop_loss_pct": 2.5,
            "take_profit_pct": 6.0,
            "min_score": 55,
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
        }

    # ── 프로퍼티 ─────────────────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self._running

    # ── 시작 / 중지 ─────────────────────────────────────────────────────────

    def start(self, settings: Optional[dict] = None):
        if self._running:
            return
        if settings:
            self.settings.update({k: v for k, v in settings.items() if k in self.settings})

        self._running = True
        self._started_at = datetime.now(KST)
        self._connector = ExchangeConnector(exchange_id="upbit", is_paper=True)

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
        logger.info("AutoTradeBot stopped")

    def update_settings(self, new_settings: dict):
        # 스타일 변경 시 프리셋 먼저 적용
        if "trading_style" in new_settings:
            style = new_settings["trading_style"]
            preset = TRADING_STYLE_PRESETS.get(style)
            if preset:
                for k, v in preset.items():
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

    # ── WebSocket 실시간 가격 모니터 ─────────────────────────────────────────

    async def _price_monitor_loop(self):
        """
        업비트 WebSocket 체결가 스트림으로 실시간 SL/TP 감시.
        연결 끊김 시 5초 대기 후 자동 재연결.
        """
        while self._running:
            try:
                await self._ws_price_monitor()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"AutoTradeBot WS: 재연결 대기 5s ({e})")
                await asyncio.sleep(5)

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

        # ── 트레일링 스탑 ────────────────────────────────────────────────────
        if self.settings.get("trailing_stop"):
            pnl_pct = (price - avg) / avg * 100
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

        # ── 일반 SL / TP ─────────────────────────────────────────────────────
        if price <= pos["stop_loss_price"]:
            await self._close_position(symbol, price, "stop_loss")
        elif not pos.get("trailing_active") and price >= pos["take_profit_price"]:
            await self._close_position(symbol, price, "take_profit")
        else:
            pos["current_price"] = price
            pos["unrealized_pnl_pct"] = round((price - avg) / avg * 100, 2)
            pos["unrealized_pnl_krw"] = round((price - avg) * pos["total_amount"])

    # ── 메인 사이클 ─────────────────────────────────────────────────────────

    async def _cycle(self):
        if self._scan_in_progress:
            return
        self._scan_in_progress = True
        try:
            # 스캔을 먼저 수행 — 포지션 보유 심볼도 포함하여 재분석
            scan_results = await scan_market(
                timeframe=self.settings["timeframe"],
                style=self.settings["trading_style"],
            )
            self._scan_results = scan_results
            self._last_scan_at = datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")

            # TODO 2: AI 시장 국면 감지 (15분 캐시 — 스캔 주기와 무관)
            await self._run_regime_detection(scan_results)

            # 기존 포지션 점검 (전략 재평가 + TODO 4: AI 청산 보조)
            await self._check_positions(scan_results)

            # 빈 슬롯에 신규 진입 (TODO 1: AI 진입 확인 포함)
            if len(self._positions) < self.settings["max_positions"]:
                await self._enter_from_scan(scan_results)
        except Exception as e:
            logger.error(f"AutoTradeBot cycle error: {e}", exc_info=True)
        finally:
            self._scan_in_progress = False

    # ── TODO 2: AI 시장 국면 감지 ────────────────────────────────────────────

    async def _run_regime_detection(self, scan_results: list[dict]):
        """
        BTC 스캔 결과 기반 국면 감지. 15분 이내 재호출 차단.
        국면이 바뀌면 min_score / trading_style 자동 조정.
        """
        import time
        if not ai_analyst.is_ai_available() or not self.settings.get("ai_regime_detection", True):
            return
        if time.time() - self._last_regime_at < 900:   # 15분 이내면 스킵
            return

        btc = next((r for r in scan_results if r["symbol"] == "BTC/KRW"), None)
        if btc is None:
            return

        try:
            # scanner 결과에서 BTC 지표 추출 (closes 직접 조회는 비용 절약을 위해 생략)
            btc_rsi = btc.get("rsi", 50.0)
            btc_price = btc.get("price", 0.0)
            # 최근 종가 근사: 단일 가격으로 패턴 대신 score/rsi 전달
            closes_approx = [btc_price] * 20   # 실제 봉 대신 현재가로 대체 (API 호출 절약)

            regime = await ai_analyst.detect_regime(
                btc_closes=closes_approx,
                btc_rsi=btc_rsi,
                btc_volume_ratio=1.0,
            )
            import time as _t
            self._last_regime_at = _t.time()

            old_regime = self._current_regime.get("regime")
            old_style  = self._current_regime.get("style")
            self._current_regime = regime

            # 국면 변경 시 설정 자동 조정
            new_style = regime["style"]
            delta     = regime["min_score_delta"]
            changed   = []

            if new_style != self.settings.get("trading_style") and new_style in TRADING_STYLE_PRESETS:
                self.update_settings({"trading_style": new_style})
                changed.append(f"스타일 {old_style}→{new_style}")

            if delta != 0:
                new_score = max(40, min(80, self.settings["min_score"] + delta))
                if new_score != self.settings["min_score"]:
                    self.settings["min_score"] = new_score
                    changed.append(f"최소점수 {new_score}")

            if changed or old_regime != regime["regime"]:
                log_entry = {
                    "at":     datetime.now(KST).strftime("%Y-%m-%d %H:%M KST"),
                    "type":   "regime_change",
                    "regime": regime["regime"],
                    "style":  new_style,
                    "reason": regime["reason"],
                    "changed": changed,
                }
                self._analysis_log.insert(0, log_entry)
                if len(self._analysis_log) > 20:
                    self._analysis_log.pop()
                logger.info(f"AutoBot AI 국면 감지: {regime['regime']} {' | '.join(changed) if changed else '변경 없음'}")
        except Exception as e:
            logger.debug(f"AutoBot 국면 감지 오류: {e}")

    async def run_scan_now(self):
        if self._scan_in_progress:
            return
        self._scan_in_progress = True
        try:
            results = await scan_market(
                timeframe=self.settings["timeframe"],
                style=self.settings["trading_style"],
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
                current_price = pos.get("current_price") or 0.0
                # 최신가가 없으면 직접 조회
                if current_price == 0.0:
                    ticker = await asyncio.wait_for(
                        self._connector.fetch_ticker(symbol), timeout=10
                    )
                    current_price = ticker["last"]
                avg = pos["avg_price"]

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
                        # 신호 약화 → 이익 구간이면 SL을 위로 당겨 이익 보호
                        pnl_pct = pos.get("unrealized_pnl_pct", 0)
                        if pnl_pct > 0:
                            protect_pct = STYLE_SL_PROTECT_PCT.get(style, 0.5)
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
                ai_pnl_threshold = min_pnl_for_ai.get(style, 1.5)
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

                # ── 자동 물타기 ──────────────────────────────────────────────
                if (
                    self.settings["auto_avg_down"]
                    and pos["avg_down_count"] < self.settings["max_avg_down"]
                    and current_price <= avg * (1 - self.settings["avg_down_threshold_pct"] / 100)
                    and self._broker.balance.get("KRW", 0) >= 5_000
                ):
                    await self._add_to_position(symbol, "avg_down", current_price)

                # ── 자동 추매 ────────────────────────────────────────────────
                elif (
                    self.settings["auto_add"]
                    and pos["add_count"] < self.settings["max_add"]
                    and current_price >= avg * (1 + self.settings["add_threshold_pct"] / 100)
                    and self._broker.balance.get("KRW", 0) >= 5_000
                ):
                    await self._add_to_position(symbol, "add", current_price)

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

            for candidate in ordered:
                if len(self._positions) >= self.settings["max_positions"]:
                    break
                symbol = candidate["symbol"]
                if symbol in self._positions:
                    continue
                if candidate["score"] < self.settings["min_score"]:
                    continue

                # 실적 게이팅
                st   = candidate.get("strategy_type", "standard")
                perf = self._strategy_performance.get(st, {})
                total = perf.get("wins", 0) + perf.get("losses", 0)
                if total >= 3 and perf["wins"] / total < 0.30:
                    logger.debug(f"AutoBot: 전략 {st} 승률 낮아 스킵 {symbol}")
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
                    if not ai_result["enter"] or ai_result["confidence"] < 65:
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

                # AI 포지션별 매매 스타일 선택 (AI 미설정 시 글로벌 스타일 유지)
                position_style = style
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
                await asyncio.sleep(0.3)
        except Exception as e:
            logger.error(f"AutoBot: enter_from_scan error: {e}", exc_info=True)

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

            krw = self._broker.balance.get("KRW", 0)
            invest_krw = krw * self.settings["position_size_pct"] / 100 * min(size_multiplier, 1.3)
            if invest_krw < 5_000:
                logger.warning(f"AutoBot: KRW 부족 ({krw:,.0f}), 진입 불가")
                return

            amount = invest_krw / price
            self._broker.execute_market_order(symbol, "buy", amount, price)

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
                # 포지션별 매매 스타일
                "position_style":       pos_style,
                "position_style_label": pos_preset["label"],
                # 메타
                "entry_at": now,
                "score": scan_result.get("score", 0),
                "signals": scan_result.get("signals", []),
                "strategy_type": scan_result.get("strategy_type", "standard"),
                "strategy_label": scan_result.get("strategy_label", "표준"),
                # 카운터
                "avg_down_count": 0,
                "add_count": 0,
            }
            logger.info(f"AutoBot: 진입 {symbol} @ {price:,.0f} ₩  수량={amount:.6f}  점수={scan_result.get('score',0)}")
        except Exception as e:
            logger.error(f"AutoBot: 진입 실패 {symbol}: {e}")

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
            krw = self._broker.balance.get("KRW", 0)
            ratio = 0.5 if mode == "avg_down" else 0.25
            invest_krw = krw * self.settings["position_size_pct"] / 100 * ratio
            invest_krw = min(invest_krw, krw * 0.5)  # 잔고 50% 초과 금지

            if invest_krw < 5_000:
                return

            amount = invest_krw / price
            self._broker.execute_market_order(symbol, "buy", amount, price)

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

    # ── 청산 ─────────────────────────────────────────────────────────────────

    async def _close_position(self, symbol: str, price: float, reason: str):
        pos = self._positions.pop(symbol, None)
        if pos is None:
            return
        try:
            amount = pos["total_amount"]
            self._broker.execute_market_order(symbol, "sell", amount, price)

            avg = pos["avg_price"]
            pnl_pct = round((price - avg) / avg * 100, 2)
            pnl_krw = round((price - avg) * amount)
            exit_at = datetime.now(KST).isoformat()

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
            }
            self._trade_log.insert(0, record)
            if len(self._trade_log) > MAX_TRADE_LOG:
                self._trade_log.pop()

            # 전략 실적 업데이트
            st = pos.get("strategy_type", "standard")
            perf = self._strategy_performance.get(st)
            if perf is not None:
                if pnl_pct > 0:
                    perf["wins"] += 1
                else:
                    perf["losses"] += 1
                perf["total_pnl"] = round(perf["total_pnl"] + pnl_pct, 2)

            # TODO 3: 연속 손절 카운터 + AI 자기 분석
            if reason == "stop_loss" and pnl_pct < 0:
                self._consecutive_losses += 1
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
                new_score = min(80, self.settings["min_score"] + result["min_score_delta"])
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
        krw = self._broker.balance.get("KRW", 0)
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
            "scan_in_progress": self._scan_in_progress,
            "positions": positions,
            "trade_log": logs[:20],
            "scan_results": self._scan_results[:10],
            "last_scan_at": self._last_scan_at,
            "balance_krw": round(krw),
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
        }


# ── 싱글턴 ──────────────────────────────────────────────────────────────────

_bot: Optional[AutoTradeBot] = None


def get_auto_bot() -> AutoTradeBot:
    global _bot
    if _bot is None:
        _bot = AutoTradeBot()
    return _bot
