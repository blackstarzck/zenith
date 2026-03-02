"""
거래소 간 가격 괴리 수집 모듈.
업비트 KRW 시세와 바이낸스 USDT 시세를 동일 KRW 기준으로 환산해
역프/김프(괴리율)를 계산합니다.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx
import pyupbit

from src.config import BinanceConfig, FxConfig

logger = logging.getLogger(__name__)


class CrossExchangeCollector:
    """업비트-바이낸스 가격 괴리 수집기."""

    def __init__(self, binance_config: BinanceConfig, fx_config: FxConfig) -> None:
        self._binance = binance_config
        self._fx = fx_config
        self._http = httpx.Client(timeout=10.0)
        self._cached_usdt_krw: float | None = None
        self._cached_rate_at: datetime | None = None

    def close(self) -> None:
        """내부 HTTP 클라이언트를 종료합니다."""
        self._http.close()

    def _to_binance_symbol(self, upbit_market: str) -> str:
        """업비트 마켓 코드(KRW-BTC)를 바이낸스 심볼(BTCUSDT)로 변환합니다."""
        if "-" not in upbit_market:
            raise ValueError(f"잘못된 업비트 마켓 형식: {upbit_market}")
        _, base = upbit_market.split("-", 1)
        return f"{base.upper()}{self._binance.quote_asset.upper()}"

    def get_upbit_price(self, market: str) -> float | None:
        """업비트 현재가(KRW)를 조회합니다."""
        price = pyupbit.get_current_price(market)
        return float(price) if price is not None else None

    def get_binance_price_usdt(self, upbit_market: str) -> float | None:
        """바이낸스 현재가(USDT)를 조회합니다."""
        symbol = self._to_binance_symbol(upbit_market)
        try:
            response = self._http.get(
                f"{self._binance.base_url}/api/v3/ticker/price",
                params={"symbol": symbol},
            )
            response.raise_for_status()
            data = response.json()
            price = data.get("price")
            if price is None:
                logger.warning("바이낸스 가격 응답 누락: %s", data)
                return None
            return float(price)
        except Exception as e:
            logger.warning("바이낸스 시세 조회 실패(%s): %s", symbol, e)
            return None

    def get_usdt_krw_rate(self) -> float:
        """USDT-KRW 환산값을 반환합니다."""
        now = datetime.now(timezone.utc)
        if (
            self._cached_usdt_krw is not None
            and self._cached_rate_at is not None
            and (now - self._cached_rate_at).total_seconds() < self._fx.refresh_interval_sec
        ):
            return self._cached_usdt_krw

        if self._fx.usdt_krw_source == "upbit":
            price = pyupbit.get_current_price(self._fx.upbit_usdt_market)
            if price is not None:
                rate = float(price)
                self._cached_usdt_krw = rate
                self._cached_rate_at = now
                return rate
            logger.warning("USDT-KRW 환율 조회 실패, fallback 사용: %s", self._fx.upbit_usdt_market)
        else:
            logger.warning("알 수 없는 환율 소스(%s), fallback 사용", self._fx.usdt_krw_source)

        self._cached_usdt_krw = float(self._fx.fallback_rate)
        self._cached_rate_at = now
        return self._cached_usdt_krw

    def get_binance_price_krw(self, upbit_market: str) -> float | None:
        """바이낸스 현재가(USDT)를 KRW로 환산해 반환합니다."""
        usdt_price = self.get_binance_price_usdt(upbit_market)
        if usdt_price is None:
            return None
        return usdt_price * self.get_usdt_krw_rate()

    @staticmethod
    def calculate_dislocation_pct(upbit_price: float, foreign_price_krw: float) -> float | None:
        """괴리율(%)을 계산합니다.

        계산식:
            (업비트 - 해외환산가) / 해외환산가 * 100
        """
        if foreign_price_krw <= 0:
            return None
        return ((upbit_price - foreign_price_krw) / foreign_price_krw) * 100.0

    def collect_snapshot(self, market: str) -> dict[str, Any] | None:
        """지정 마켓의 거래소 간 괴리 스냅샷을 수집합니다."""
        upbit_price = self.get_upbit_price(market)
        foreign_price_krw = self.get_binance_price_krw(market)
        if upbit_price is None or foreign_price_krw is None:
            logger.warning("괴리 스냅샷 수집 실패: %s", market)
            return None

        dislocation_pct = self.calculate_dislocation_pct(upbit_price, foreign_price_krw)
        return {
            "market": market,
            "binance_symbol": self._to_binance_symbol(market),
            "upbit_price": upbit_price,
            "foreign_price_krw": foreign_price_krw,
            "usdt_krw_rate": self.get_usdt_krw_rate(),
            "dislocation_pct": dislocation_pct,
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }

