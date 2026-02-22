"""
Upbit 데이터 수집 모듈.
REST API로 캔들/호가/시세 데이터를 수집하고,
WebSocket으로 실시간 체결 데이터를 스트리밍합니다.
"""

from __future__ import annotations

import logging
import time
import re
from typing import Any

import pyupbit
import pandas as pd
import requests

from src.config import UpbitConfig

logger = logging.getLogger(__name__)

# 업비트 API 요청 제한: sec < 2이면 슬립
_MIN_REQ_SEC_THRESHOLD = 2


class UpbitCollector:
    """Upbit REST API 데이터 수집기."""

    def __init__(self, config: UpbitConfig) -> None:
        if not config.access_key or not config.secret_key:
            raise ValueError("UPBIT_ACCESS_KEY 및 UPBIT_SECRET_KEY가 필요합니다.")
        self._upbit = pyupbit.Upbit(config.access_key, config.secret_key)

    # ── 시세 데이터 ──────────────────────────────────────────

    def get_ohlcv(
        self,
        symbol: str,
        interval: str = "minute15",
        count: int = 200,
    ) -> pd.DataFrame:
        """OHLCV 캔들 데이터를 DataFrame으로 반환합니다.

        Args:
            symbol: 마켓 코드 (예: "KRW-BTC")
            interval: 캔들 간격 ("minute1", "minute15", "day" 등)
            count: 캔들 수 (최대 200)

        Returns:
            open, high, low, close, volume 컬럼의 DataFrame
        """
        df = pyupbit.get_ohlcv(symbol, interval=interval, count=count)
        if df is None or df.empty:
            logger.warning("OHLCV 데이터 없음: %s", symbol)
            return pd.DataFrame()
        return df

    def get_current_price(self, symbol: str) -> float | None:
        """현재 시세를 반환합니다."""
        price = pyupbit.get_current_price(symbol)
        return float(price) if price is not None else None

    def get_current_prices(self, symbols: list[str]) -> dict[str, float]:
        """여러 종목의 현재 시세를 일괄 조회합니다."""
        prices = pyupbit.get_current_price(symbols)
        if isinstance(prices, dict):
            return {k: float(v) for k, v in prices.items()}
        return {}

    def get_orderbook(self, symbol: str) -> dict[str, Any]:
        """호가 정보를 반환합니다."""
        orderbook = pyupbit.get_orderbook(symbol)
        if not orderbook:
            logger.warning("호가 데이터 없음: %s", symbol)
            return {}
        # pyupbit는 리스트로 반환, 첫 번째 항목 사용
        if isinstance(orderbook, list):
            return orderbook[0] if orderbook else {}
        return orderbook

    # ── 거래 대금 기준 종목 추출 ─────────────────────────────

    def get_top_volume_symbols(self, top_n: int = 10) -> list[str]:
        """KRW 마켓에서 거래 대금 상위 N개 종목을 반환합니다.

        업비트 Ticker API를 사용하여 전종목 거래대금을 일괄 조회합니다.
        (기존 개별 OHLCV 조회 대비 ~50배 빠름)
        """
        tickers = pyupbit.get_tickers(fiat="KRW")
        if not tickers:
            return []

        try:
            # 업비트 Ticker API로 전종목 거래대금 일괄 조회
            all_data: list[dict] = []
            batch_size = 100  # API 최대 100개씩 조회
            for i in range(0, len(tickers), batch_size):
                batch = tickers[i:i + batch_size]
                markets_param = ",".join(batch)
                resp = requests.get(
                    "https://api.upbit.com/v1/ticker",
                    params={"markets": markets_param},
                    timeout=10,
                )
                resp.raise_for_status()
                all_data.extend(resp.json())
                if i + batch_size < len(tickers):
                    time.sleep(0.1)  # Rate limit 방어

            # 거래대금 기준 정렬
            volumes = [
                (item["market"], float(item.get("acc_trade_price_24h", 0)))
                for item in all_data
                if item.get("market", "").startswith("KRW-")
            ]
            volumes.sort(key=lambda x: x[1], reverse=True)
            top_symbols = [sym for sym, _ in volumes[:top_n]]
            logger.info("거래 대금 상위 %d: %s", top_n, top_symbols)
            return top_symbols

        except Exception as e:
            logger.error("Ticker API 거래대금 조회 실패, 기존 방식 사용: %s", e)
            return self._get_top_volume_symbols_legacy(top_n)

    def _get_top_volume_symbols_legacy(self, top_n: int = 10) -> list[str]:
        """거래대금 상위 종목을 개별 OHLCV 조회로 추출합니다 (폴백)."""
        tickers = pyupbit.get_tickers(fiat="KRW")
        if not tickers:
            return []

        volumes: list[tuple[str, float]] = []
        for ticker in tickers:
            try:
                info = pyupbit.get_ohlcv(ticker, interval="day", count=1)
                if info is not None and not info.empty:
                    acc_trade_price = float(info["value"].iloc[-1]) if "value" in info.columns else 0.0
                    volumes.append((ticker, acc_trade_price))
            except Exception:
                continue
            # Rate limit 방어
            time.sleep(0.1)

        volumes.sort(key=lambda x: x[1], reverse=True)
        top_symbols = [sym for sym, _ in volumes[:top_n]]
        logger.info("거래 대금 상위 %d (레거시): %s", top_n, top_symbols)
        return top_symbols

    # ── 계좌 정보 ────────────────────────────────────────────

    def get_balances(self) -> list[dict[str, Any]]:
        """전체 잔고를 조회합니다."""
        return self._upbit.get_balances()

    def get_balance(self, symbol: str) -> float:
        """특정 코인의 보유 수량을 반환합니다."""
        return float(self._upbit.get_balance(symbol))

    def get_krw_balance(self) -> float:
        """KRW 잔고를 반환합니다."""
        balance = self._upbit.get_balance("KRW")
        if balance is None:
            logger.warning("KRW 잔고 조회 실패, 0.0 반환")
            return 0.0
        return float(balance)

    def get_avg_buy_price(self, symbol: str) -> float:
        """특정 코인의 평균 매수 단가를 반환합니다."""
        return float(self._upbit.get_avg_buy_price(symbol))

    # ── pyupbit 인스턴스 노출 (주문 실행용) ──────────────────

    @property
    def upbit(self) -> pyupbit.Upbit:
        """pyupbit.Upbit 인스턴스를 반환합니다 (주문 실행 모듈에서 사용)."""
        return self._upbit
