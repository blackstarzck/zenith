"""
Zenith 전역 설정 관리.
환경 변수(.env)로부터 모든 민감 정보를 로드하고,
전략 파라미터와 리스크 한도를 중앙 집중 관리합니다.
"""

import os
from dataclasses import dataclass, field, asdict, fields as dc_fields
from dotenv import load_dotenv

load_dotenv(".env.backend")


@dataclass(frozen=True)
class UpbitConfig:
    access_key: str = field(default_factory=lambda: os.getenv("UPBIT_ACCESS_KEY", ""))
    secret_key: str = field(default_factory=lambda: os.getenv("UPBIT_SECRET_KEY", ""))
    base_url: str = "https://api.upbit.com"
    ws_url: str = "wss://api.upbit.com/websocket/v1"


@dataclass(frozen=True)
class SupabaseConfig:
    url: str = field(default_factory=lambda: os.getenv("SUPABASE_URL", ""))
    secret_key: str = field(default_factory=lambda: os.getenv("SUPABASE_SECRET_KEY", ""))


@dataclass(frozen=True)
class KakaoConfig:
    rest_api_key: str = field(default_factory=lambda: os.getenv("KAKAO_REST_API_KEY", ""))
    client_secret: str = field(default_factory=lambda: os.getenv("KAKAO_CLIENT_SECRET", ""))
    access_token: str = field(default_factory=lambda: os.getenv("KAKAO_ACCESS_TOKEN", ""))
    refresh_token: str = field(default_factory=lambda: os.getenv("KAKAO_REFRESH_TOKEN", ""))


@dataclass(frozen=True)
class StrategyParams:
    """평균 회귀 전략 핵심 파라미터."""
    # 볼린저 밴드
    bb_period: int = 20
    bb_std_dev: float = 2.0

    # RSI
    rsi_period: int = 14
    rsi_oversold: float = 30.0
    rsi_overbought: float = 70.0

    # ATR 기반 동적 손절
    atr_period: int = 14
    atr_stop_multiplier: float = 2.5

    # 변동성 과부하 필터: 24h 변동성이 20일 평균의 N배 초과 시 매매 중단
    volatility_overload_ratio: float = 2.0

    # 분할 익절 비율
    take_profit_ratio_1st: float = 0.5  # 중앙선 도달 시 50% 매도
    take_profit_ratio_2nd: float = 1.0  # 상단선 도달 시 나머지 전량 매도

    # 최소 익절 마진 (수수료 0.1% + 알파 0.2% = 0.3%)
    min_profit_margin: float = 0.003

    # 거래 대금 상위 종목 수
    top_volume_count: int = 10

    # RSI 진입 상한 오프셋 (RSI > rsi_oversold + offset 이면 진입 차단)
    rsi_entry_ceiling_offset: float = 5.0

    # MA 추세 필터 기간
    ma_short_period: int = 20
    ma_long_period: int = 50

    # 변동성 과부하 윈도우 (15분봉 기준)
    vol_short_window: int = 16    # 4시간 (15분봉 × 16)
    vol_long_window: int = 192    # ~2일 (15분봉 × 192)

    # RSI 기울기 계산 lookback
    rsi_slope_lookback: int = 3

    # ADX 추세 강도 필터
    adx_period: int = 14
    adx_trend_threshold: float = 25.0  # ADX > 이 값이면 강한 추세로 판단

    # 시장 레짐 감지기
    regime_adx_trending_threshold: float = 25.0  # ADX ≥ 이 값이면 추세장
    regime_vol_overload_ratio: float = 2.0       # 변동성 비율 ≥ 이 값이면 변동성 폭발
    regime_lookback_candles: int = 3             # 히스테리시스 룩백 (다수결 캔들 수)
    def to_dict(self) -> dict:
        """StrategyParams를 딕셔너리로 변환합니다."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "StrategyParams":
        """딕셔너리로부터 StrategyParams를 생성합니다 (미지정 필드는 기본값)."""
        defaults = asdict(cls())
        valid_names = {f.name for f in dc_fields(cls)}
        for k, v in data.items():
            if k in valid_names and v is not None:
                defaults[k] = v
        return cls(**defaults)

@dataclass(frozen=True)
class RiskParams:
    """리스크 관리 파라미터."""
    max_position_ratio: float = 0.20       # 종목당 최대 자산 비중 20%
    max_concurrent_positions: int = 5       # 최대 동시 보유 종목 수
    daily_loss_limit_ratio: float = 0.05    # 일일 최대 손실 비율 5%
    unfilled_timeout_sec: int = 30          # 미체결 주문 타임아웃 30초 (시장가 기준)
    min_order_amount_krw: int = 5000        # 업비트 최소 주문 금액

    # 켈리 공식 포지션 사이징
    kelly_multiplier: float = 0.5        # Half-Kelly (0.5배)
    kelly_min_trades: int = 30           # 최소 샘플 수 (미달 시 고정비율 폴백)

    # 슬리피지 허용 한도
    slippage_threshold_bps: float = 50.0  # 50bps (0.5%) 초과 시 진입 거부


@dataclass(frozen=True)
class AppConfig:
    upbit: UpbitConfig = field(default_factory=UpbitConfig)
    supabase: SupabaseConfig = field(default_factory=SupabaseConfig)
    kakao: KakaoConfig = field(default_factory=KakaoConfig)
    strategy: StrategyParams = field(default_factory=StrategyParams)
    risk: RiskParams = field(default_factory=RiskParams)

    # 메인 루프 간격 (초)
    loop_interval_sec: int = 10
    # 캔들 수집 단위
    candle_interval: str = "minute15"
    candle_count: int = 200


def load_config() -> AppConfig:
    """애플리케이션 설정을 로드합니다."""
    return AppConfig()
