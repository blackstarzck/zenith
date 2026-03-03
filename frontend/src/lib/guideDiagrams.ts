/**
 * 가이드 페이지 Mermaid 다이어그램 데이터
 *
 * 출처:
 *   - docs/System-Architecture-Design.md (시스템 아키텍처, 데이터 흐름)
 *   - docs/Algorithm_Specification.md (진입/청산 파이프라인)
 */

/** 섹션 key별 다이어그램 목록 */
export const GUIDE_DIAGRAMS: Record<string, { title: string; chart: string }[]> = {
  // ── 전략 개요: 시스템 아키텍처 + 데이터 흐름 ──
  overview: [
    {
      title: '시스템 아키텍처 개요',
      chart: `graph TB
    subgraph EXT["외부 서비스"]
        UPBIT["Upbit API\\n(REST + WebSocket)"]
        KAKAO["KakaoTalk API\\n(나에게 보내기)"]
    end

    subgraph PY["Python 백엔드 — 로컬 상시 구동"]
        ORCH["Orchestrator\\n10초 메인 루프"]
        COLL["Data Collector\\n시세/호가 수집"]
        STRAT["Strategy Engine\\n6-팩터 스코어링"]
        REGIME["Regime Detector\\nBTC 시장 레짐"]
        RISK["Risk Manager\\n켈리/리스크 관리"]
        EXEC["Order Executor\\n시장가 주문 집행"]
        NOTI["Notifier\\n카카오톡 알림"]
    end

    subgraph DB["Supabase — PostgreSQL"]
        TABLES["trades / daily_stats / bot_state\\nsystem_logs / price_snapshots\\nbalance_snapshots"]
    end

    subgraph FE["React + AntD 대시보드"]
        HOOKS["useSupabase\\nRealtime 구독"]
        TICKER["useUpbitTicker\\nWebSocket 시세"]
        UI["Dashboard UI"]
    end

    UPBIT -->|"REST: 시세/호가/잔고"| COLL
    ORCH --> COLL
    ORCH --> STRAT
    ORCH --> REGIME
    ORCH --> RISK
    ORCH --> EXEC
    EXEC -->|"시장가 주문"| UPBIT
    EXEC --> NOTI
    NOTI -->|"매매 알림"| KAKAO
    COLL --> TABLES
    EXEC --> TABLES
    ORCH --> TABLES
    TABLES -->|"Realtime 구독"| HOOKS
    UPBIT -->|"WebSocket 시세"| TICKER
    HOOKS --> UI
    TICKER --> UI
    UI -->|"strategy_params 수정"| TABLES
    TABLES -.->|"~1분 폴링 hot reload"| ORCH`,
    },
    {
      title: '데이터 흐름 (5단계 파이프라인)',
      chart: `flowchart TD
    subgraph COLLECT["1단계: 데이터 수집"]
        A1["Upbit REST API"] -->|"Ticker 배치 100개"| A2["거래대금 상위 10개 심볼"]
        A1 -->|"15분봉 200개"| A3["OHLCV 캔들 데이터"]
        A1 -->|"호가창 조회"| A4["Orderbook 데이터"]
    end

    subgraph COMPUTE["2단계: 전략 연산"]
        A3 --> B1["지표 계산\\nBB / RSI / ATR / ADX / MA"]
        B1 --> B2["6-팩터 스코어링 → 매매 신호"]
    end

    subgraph EXECUTE["3단계: 주문 집행"]
        A4 --> C1["슬리피지 검증\\n50bps 이하"]
        B2 --> C1
        C1 --> C2["시장가 주문\\nUpbit API"]
    end

    subgraph STORE["4단계: 저장 및 알림"]
        C2 --> D1["Supabase DB 기록"]
        C2 --> D2["KakaoTalk 매매 알림"]
    end

    subgraph VIEW["5단계: 실시간 시각화"]
        D1 -->|"Realtime 구독"| E1["React 대시보드"]
        E2["Upbit WebSocket\\n500ms 버퍼"] --> E1
        E1 -->|"전략 파라미터 수정"| D1
    end`,
    },
  ],

  // ── 매수 진입 조건: 진입 파이프라인 ──
  entry: [
    {
      title: '매수 진입 파이프라인',
      chart: `flowchart TD
    subgraph FILTER["1단계: 시장 필터링"]
        F1["거래대금 상위 10개 심볼 추출\\n(Ticker 배치 100개 → 정렬)"] --> F2["심볼별 OHLCV 수집\\n(15분봉 × 200개)"]
        F2 --> F3["지표 스냅샷 계산\\nBB / RSI / ATR / ADX / MA"]
        F3 --> F4{"쿨다운 확인\\n(최근 매도 후 대기)"}
        F4 -->|"대기 중"| F4X["⛔ 진입 스킵"]
        F4 -->|"통과"| F5{"리스크 사전 검증\\ncan_enter()"}
        F5 -->|"거부\\n(일일정지/보유중/최대5종목)"| F5X["⛔ 진입 불가"]
        F5 -->|"통과"| SCORE
    end

    subgraph SCORE["2단계: 6-팩터 스코어링"]
        S1["변동성 스코어"] --> S7["가중 평균 합산\\ntotal_score"]
        S2["MA 추세 스코어"] --> S7
        S3["ADX 스코어"] --> S7
        S4["BB 복귀 스코어"] --> S7
        S5["RSI 기울기 스코어"] --> S7
        S6["RSI 수준 스코어"] --> S7
        S7 --> S8{"total_score ≥\\neffective_threshold?"}
        S8 -->|"미달"| S8X["⛔ 신호 없음"]
        S8 -->|"충족"| SIZING
    end

    subgraph REGIME["레짐 오프셋 적용"]
        R1["BTC 15분봉 분석"] --> R2{"시장 레짐 판정"}
        R2 -->|"횡보장"| R3["오프셋 +0"]
        R2 -->|"추세장\\nADX≥25"| R4["오프셋 +15"]
        R2 -->|"변동성 폭발\\nvol≥2×"| R5["오프셋 +25"]
        R3 & R4 & R5 --> R6["effective_threshold\\n= min(base + offset, 99)"]
    end

    R6 -.->|"임계치 전달"| S8

    subgraph SIZING["3단계: 포지션 사이징"]
        K1{"매매 기록 ≥ 30회?"}
        K1 -->|"예"| K2["Kelly Criterion\\nHalf-Kelly (50%) 적용"]
        K1 -->|"아니오"| K3["고정 비중 20%"]
        K2 & K3 --> K4["투입 금액 산출"]
    end

    subgraph SLIP["4단계: 슬리피지 검증"]
        K4 --> SL1["호가창 Walk-the-book\\n시뮬레이션"]
        SL1 --> SL2{"슬리피지 ≤ 50bps?"}
        SL2 -->|"초과"| SL3["⛔ 매수 포기"]
        SL2 -->|"이하"| BUY["✅ 시장가 매수 집행"]
    end

    subgraph POST["5단계: 사후 처리"]
        BUY --> P1["체결 대기 (2초 폴링)"]
        P1 --> P2["Supabase 거래 기록"]
        P1 --> P3["KakaoTalk 매수 알림"]
        P1 --> P4["Risk Manager 포지션 등록"]
    end`,
    },
  ],

  // ── 매도/청산 규칙: 청산 파이프라인 ──
  exit: [
    {
      title: '청산 파이프라인',
      chart: `flowchart TD
    subgraph MONITOR["포지션 모니터링"]
        M1["보유 포지션 순회"] --> M2["OHLCV 수집 (15분봉 × 200)"]
        M2 --> M3["지표 스냅샷 갱신\\nBB / RSI / ATR / ADX"]
        M3 --> M4["트레일링 고점 갱신\\nupdate_trailing_high()"]
    end

    subgraph HARD["하드 룰 (즉시 매도)"]
        M4 --> H1{"ATR 손절\\n현재가 ≤ 진입가 - ATR×레짐배수\\n(횡보2.8/추세2.2/변동2.5)?"}
        H1 -->|"예"| H2["🔴 즉시 전량 매도\\n(STOP_LOSS)"]
        H1 -->|"아니오"| H3{"트레일링 스탑\\n(반매도 후 활성)\\n현재가 ≤ max(고점-ATR×적응배수, 본전+마진)?"}
        H3 -->|"예"| H4["🔴 잔량 전량 매도\\n(TRAILING_STOP)"]
        H3 -->|"아니오"| H5{"이미 반매도\\n(half_sold)?"}
        H5 -->|"예"| H6["⏳ 홀딩 유지\\n(스코어링 비활성, 트레일링 대기)"]
        H5 -->|"아니오"| EXIT_SCORE
    end

    subgraph EXIT_SCORE["4-팩터 청산 스코어링"]
        E1["RSI 수준 스코어"] --> E5["가중 평균 합산\\nexit_score"]
        E2["BB 위치 스코어"] --> E5
        E3["수익률 스코어"] --> E5
        E4["ADX 스코어"] --> E5
        E5 --> E6{"exit_score ≥\\n실효 임계치?"}
        E6 -->|"미달"| E7["⏳ 홀딩 유지"]
        E6 -->|"충족"| E8{"적응형 최소 수익률\\nadaptive_margin 충족?"}
        E8 -->|"미달"| E7
        E8 -->|"충족"| E9{"품질 게이트 통과?\\n(BB 중앙선 도달 OR 초과수익)"}
        E9 -->|"미통과"| E7
        E9 -->|"통과"| E10["🟡 40% 매도\\n(SELL_HALF)"]
    end

    subgraph POST["사후 처리"]
        H2 & H4 & E10 --> P1["실제 잔고 조회\\nget_balance()"]
        P1 --> P2["시장가 매도 집행"]
        P2 --> P3["PnL 계산 (수수료 반영)"]
        P3 --> P4["일일 손실 한도 체크\\nrecord_realized_pnl()"]
        P3 --> P5["Supabase 거래 기록"]
        P3 --> P6["KakaoTalk 매도 알림"]
        E10 --> P7["mark_half_sold()\\n→ 트레일링 활성화"]
    end`,
    },
  ],

  // ── 시장 레짐: 레짐 감지 흐름 ──
  regime: [
    {
      title: '시장 레짐 감지 및 오프셋 적용',
      chart: `flowchart TD
    subgraph DETECT["레짐 감지 (10분마다)"]
        D1["BTC-KRW 15분봉 200개 수집"] --> D2["변동성 비율 계산\\n(단기 16캔들 / 장기 192캔들)"]
        D1 --> D3["ADX 계산\\n(추세 강도)"]
        D2 --> D4{"vol_ratio ≥ 2.0?"}
        D4 -->|"예"| D5["🔴 변동성 폭발\\n(VOLATILE)"]
        D4 -->|"아니오"| D6{"ADX ≥ 25?"}
        D6 -->|"예"| D7["🟡 추세장\\n(TRENDING)"]
        D6 -->|"아니오"| D8["🟢 횡보장\\n(RANGING)"]
    end

    subgraph HYSTERESIS["히스테리시스 (떨림 방지)"]
        D5 & D7 & D8 --> H1["최근 3캔들 다수결 투표"]
        H1 --> H2["최종 레짐 확정"]
    end

    subgraph OFFSET["진입 임계치 조정"]
        H2 --> O1{"확정 레짐?"}
        O1 -->|"횡보"| O2["오프셋 +0\\n(기본 임계치 유지)"]
        O1 -->|"추세"| O3["오프셋 +15\\n(더 확실한 기회만)"]
        O1 -->|"변동성"| O4["오프셋 +25\\n(매우 강한 신호만)"]
        O2 & O3 & O4 --> O5["effective_threshold\\n= min(base + offset, 99)"]
    end

    O5 --> RESULT["매수 스코어링에 적용\\n→ evaluate_entry()"]`,
    },
  ],
};
