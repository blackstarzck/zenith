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
class BinanceConfig:
    """바이낸스 시세 비교용 설정."""
    api_key: str = field(default_factory=lambda: os.getenv("BINANCE_API_KEY", ""))
    secret_key: str = field(default_factory=lambda: os.getenv("BINANCE_SECRET_KEY", ""))
    base_url: str = "https://api.binance.com"
    ws_url: str = "wss://stream.binance.com:9443/ws"
    quote_asset: str = "USDT"


@dataclass(frozen=True)
class FxConfig:
    """환율(USDT-KRW) 환산 설정."""
    usdt_krw_source: str = field(default_factory=lambda: os.getenv("USDT_KRW_SOURCE", "upbit"))
    upbit_usdt_market: str = field(default_factory=lambda: os.getenv("UPBIT_USDT_MARKET", "KRW-USDT"))
    fallback_rate: float = field(default_factory=lambda: float(os.getenv("USDT_KRW_FALLBACK_RATE", "1300")))
    refresh_interval_sec: int = field(default_factory=lambda: int(os.getenv("USDT_KRW_REFRESH_INTERVAL_SEC", "5")))


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
class SentimentConfig:
    """뉴스 감성 분석 설정 (Groq + CryptoPanic)."""
    # API 키
    groq_api_key: str = field(default_factory=lambda: os.getenv("GROQ_API_KEY", ""))
    cryptopanic_api_key: str = field(default_factory=lambda: os.getenv("CRYPTOPANIC_API_KEY", ""))
    # Groq 모델
    groq_model: str = "llama-3.1-8b-instant"
    # 뉴스 폴링 간격 (틱 수 기준, 10초 루프 × 30 = 약 5분)
    poll_interval_ticks: int = 30
    # 감성 분석 대상 코인 (CryptoPanic currencies 파라미터)
    target_currencies: str = "BTC,ETH,XRP,SOL,DOGE,ADA"
    # Groq API 타임아웃 (초)
    api_timeout_sec: int = 30
    # 한 번에 가져올 뉴스 수
    max_news_per_poll: int = 10
    # 사후 검증 기준 시간 (분)
    verification_horizon_minutes: int = 60
    verification_horizon_short_minutes: int = 30
    verification_horizon_long_minutes: int = 180
    horizon_ab_confidence_threshold: float = 80.0
    # HOLD/WAIT 판정의 허용 변동폭 (%), 절대값 기준
    hold_neutral_threshold_pct: float = 0.3
    directional_decision_min_confidence: float = 80.0
    directional_decision_min_abs_score: float = 0.45
    directional_neutral_band_pct: float = 0.15


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
    atr_stop_multiplier: float = 3.0
    atr_stop_multiplier_ranging: float = 2.8   # 횡보장: 노이즈 허용 여유
    atr_stop_multiplier_trending: float = 2.2  # 추세장: 역추세 빠른 탈출
    atr_stop_multiplier_volatile: float = 2.5  # 변동성 폭발: 중립

    # 변동성 과부하 필터: 24h 변동성이 20일 평균의 N배 초과 시 매매 중단
    volatility_overload_ratio: float = 2.0


    # 최소 익절 마진 (수수료 0.1% + 알파 0.35% = 0.45%)
    min_profit_margin: float = 0.0045

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
    regime_lookback_candles: int = 2             # 히스테리시스 룩백 (다수결 캔들 수)
    # 레짐별 진입 임계값 (절대값, 0~100)
    # 각 레짐에서 total_score가 이 값 이상이면 BUY 신호 발생
    entry_threshold_trending: float = 70.0   # 추세장: 추세 방향 진입이 유리하므로 낮은 임계값
    entry_threshold_ranging: float = 75.0    # 횡보장: 평균 회귀 전략의 기본 임계값
    entry_threshold_volatile: float = 80.0   # 변동성 폭발: 위험 높으므로 높은 임계값
    regime_min_hold_minutes: int = 20  # 레짐 변경 후 최소 유지 시간 (분) — 플래핑 방지

    # 스코어링 가중치 (0.0 = 비활성, 높을수록 비중 큼)
    w_volatility: float = 0.8       # 상시 만점 경향 → 비중 하향
    w_ma_trend: float = 1.2         # 추세 컨텍스트 강화
    w_adx: float = 1.1              # 추세 강도 반영 강화
    w_bb_recovery: float = 0.9      # 상시 만점 경향 → 비중 하향
    w_rsi_slope: float = 1.2        # 과매도 품질 반영 강화
    w_rsi_level: float = 1.3        # 과매도 수준 가장 중요

    # 스코어링 진입 임계치 (레거시 호환용 — 실제 로직은 entry_threshold_* 사용)
    # from_dict()에서 이전 설정값이 들어올 수 있으므로 필드 유지
    entry_score_threshold: float = 75.0
    # 매도 청산 스코어링 가중치 (0.0 = 비활성, 높을수록 비중 큼)
    w_exit_rsi_level: float = 0.9       # RSI 과매수 (보조 시그널)
    w_exit_bb_position: float = 1.2     # BB 상단 접근 (평균복귀 완료 신호 강화)
    w_exit_profit_pct: float = 1.4      # 수익률 우선 (손익비 개선 핵심)
    w_exit_adx_trend: float = 0.8       # 강한 추세 경고 (과민 반응 완화)

    # 매도 청산 임계치 (0~100, 가중합산 스코어가 이 값 이상이면 익절)
    exit_score_threshold: float = 73.0

    # 트레일링 스탑 (1차 익절 후 활성화)
    trailing_stop_atr_multiplier: float = 2.4  # 고점 대비 ATR * N 하락 시 전량 매도

    # 분할 매도 비율 (SELL_HALF 시 매도 비율)
    take_profit_sell_ratio: float = 0.4

    def get_atr_multiplier(self, regime: str = "ranging") -> float:
        """레짐에 따른 ATR 손절 배수를 반환합니다."""
        if regime == "ranging":
            return self.atr_stop_multiplier_ranging
        elif regime == "trending":
            return self.atr_stop_multiplier_trending
        elif regime == "volatile":
            return self.atr_stop_multiplier_volatile
        return self.atr_stop_multiplier  # 알 수 없는 레짐 → 기본 폴백

    def get_entry_threshold(self, regime: str = "ranging") -> float:
        """레짐에 따른 진입 임계값을 반환합니다."""
        if regime == "trending":
            return self.entry_threshold_trending
        elif regime == "volatile":
            return self.entry_threshold_volatile
        return self.entry_threshold_ranging  # ranging 또는 알 수 없는 레짐 → 횡보장 기본값

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
    binance: BinanceConfig = field(default_factory=BinanceConfig)
    fx: FxConfig = field(default_factory=FxConfig)
    supabase: SupabaseConfig = field(default_factory=SupabaseConfig)
    kakao: KakaoConfig = field(default_factory=KakaoConfig)
    strategy: StrategyParams = field(default_factory=StrategyParams)
    risk: RiskParams = field(default_factory=RiskParams)
    sentiment: SentimentConfig = field(default_factory=SentimentConfig)

    # 메인 루프 간격 (초)
    loop_interval_sec: int = 10
    # 캔들 수집 단위
    candle_interval: str = "minute15"
    candle_count: int = 200


def load_config() -> AppConfig:
    """애플리케이션 설정을 로드합니다."""
    return AppConfig()
