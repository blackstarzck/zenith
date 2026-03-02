/**
 * 가이드 페이지 콘텐츠 데이터
 *
 * 출처:
 *   - docs/Strategy-Parameters-Guide.md
 *   - docs/Algorithm_Specification.md
 *   - frontend/src/lib/strategyParams.ts (프리셋 수치)
 */

/** 가이드 페이지 Collapse 섹션 구조 */
export interface GuideSection {
  key: string;
  title: string;
  content: {
    paragraphs: string[];
    tables?: {
      title?: string;
      columns: { title: string; dataIndex: string; key: string }[];
      data: Record<string, string | number>[];
    }[];
    highlights?: string[];
    formulas?: string[];
  };
}

/** 가이드 페이지 7개 섹션 콘텐츠 */
export const GUIDE_SECTIONS: GuideSection[] = [
  // ── Section 1: 전략 개요 ──
  {
    key: 'overview',
    title: '전략 개요',
    content: {
      paragraphs: [
        'Zenith의 기본 아이디어는 "많이 떨어진 가격이 다시 평균 근처로 돌아올 수 있다"는 점을 활용하는 것입니다. 다만 아무 때나 사지 않고, 반등 신호가 충분히 모였을 때만 진입하도록 안전장치를 함께 둡니다.',
        '설정은 크게 두 가지입니다. 첫째는 지표를 "어떻게 계산할지", 둘째는 계산된 지표를 보고 "언제 매수할지"입니다. 비유하면 첫째는 온도계 눈금을 맞추는 일, 둘째는 에어컨 목표 온도를 정하는 일입니다.',
        '파라미터 설정(상단)을 바꾸면 지표 숫자 자체가 달라집니다. 반대로 매수 조건(하단)을 바꾸면 같은 숫자를 보더라도 진입 기준이 달라집니다.',
      ],
      tables: [
        {
          title: '파라미터 설정 vs 매수 진입 조건 비교',
          columns: [
            { title: '구분', dataIndex: 'category', key: 'category' },
            { title: '파라미터 설정', dataIndex: 'paramSetting', key: 'paramSetting' },
            { title: '매수 진입 조건', dataIndex: 'entryCondition', key: 'entryCondition' },
          ],
          data: [
            { key: '1', category: '바꾸는 것', paramSetting: '지표 계산 공식의 입력값', entryCondition: '지표를 보는 눈높이와 기준점' },
            { key: '2', category: '영향', paramSetting: 'BB 모양, RSI 수치, 손절 거리', entryCondition: '같은 시장 상황에서 매수 여부 결정' },
            { key: '3', category: '비유', paramSetting: '온도계 눈금 조정', entryCondition: '에어컨 설정 온도 변경' },
            { key: '4', category: '코드 위치', paramSetting: 'indicators.py에서 계산 시 사용', entryCondition: 'engine.py의 evaluate_entry()에서 사용' },
          ],
        },
      ],
      highlights: [
        '이 전략은 가격이 통계적 정상 범위를 벗어났을 때 평균으로 회귀하려는 성질을 이용합니다. 추세가 완전히 무너지는 상황을 회피하기 위해 \'진입 확증\'과 \'동적 위험 관리\'를 결합합니다.',
      ],
    },
  },

  // ── Section 2: 매수 진입 조건 ──
  {
    key: 'entry',
    title: '매수 진입 조건',
    content: {
      paragraphs: [
        '가격이 싸 보인다고 바로 매수하지 않습니다. 하락이 둔화되고 반등 가능성이 보이는지 여러 신호를 함께 확인합니다.',
        '봇은 6개 항목을 0~100점으로 채점하고, 가중 평균 점수가 기준점(임계값)을 넘을 때만 매수합니다. 한 항목이 약해도 다른 항목이 강하면 보완될 수 있어, 단일 조건 방식보다 유연합니다.',
      ],
      tables: [
        {
          title: '6가지 스코어링 요소',
          columns: [
            { title: '요소', dataIndex: 'factor', key: 'factor' },
            { title: '100점 (유리)', dataIndex: 'score100', key: 'score100' },
            { title: '0점 (불리)', dataIndex: 'score0', key: 'score0' },
            { title: '스코어 공식', dataIndex: 'formula', key: 'formula' },
            { title: '가중치 변수', dataIndex: 'weight', key: 'weight' },
          ],
          data: [
            { key: '1', factor: '변동성', score100: 'vol_ratio ≤ 1.0', score0: 'vol_ratio ≥ 3.0', formula: '(3.0 - ratio) / 2.0 × 100', weight: 'w_volatility' },
            { key: '2', factor: 'MA 추세', score100: '20일선 > 50일선', score0: '20일선 < 50일선', formula: '상승=100, 하락=0, 데이터부족=50', weight: 'w_ma_trend' },
            { key: '3', factor: 'ADX', score100: 'ADX ≤ 15', score0: 'ADX ≥ 40', formula: '(40 - adx) / 25 × 100', weight: 'w_adx' },
            { key: '4', factor: 'BB 복귀', score100: '하단 이탈 후 복귀', score0: '이탈 이력 없음', formula: '복귀=100, 이탈중=30, 없음=0', weight: 'w_bb_recovery' },
            { key: '5', factor: 'RSI 기울기', score100: 'slope > 3.0', score0: 'slope ≤ 0', formula: 'slope / 3.0 × 100', weight: 'w_rsi_slope' },
            { key: '6', factor: 'RSI 레벨', score100: 'RSI ≤ 20', score0: 'RSI ≥ 45', formula: '(45 - rsi) / 25 × 100', weight: 'w_rsi_level' },
          ],
        },
        {
          title: '임계값에 따른 매매 성향',
          columns: [
            { title: '임계값', dataIndex: 'threshold', key: 'threshold' },
            { title: '성격', dataIndex: 'style', key: 'style' },
            { title: '설명', dataIndex: 'description', key: 'description' },
          ],
          data: [
            { key: '1', threshold: 55, style: '공격적', description: '조금만 반등 기미가 보여도 매수. 거래 횟수 많고 승률 낮음.' },
            { key: '2', threshold: 70, style: '균형 (기본값)', description: '여러 지표가 공통적으로 반등을 가리킬 때 진입.' },
            { key: '3', threshold: 90, style: '보수적', description: '모든 조건이 완벽하게 맞아야 매수. 거래 횟수 적지만 확실한 자리만.' },
          ],
        },
        {
          title: '백테스트 결과 (임계값별 성과)',
          columns: [
            { title: '임계값', dataIndex: 'threshold', key: 'threshold' },
            { title: '거래 수', dataIndex: 'trades', key: 'trades' },
            { title: '승률', dataIndex: 'winRate', key: 'winRate' },
            { title: '수익률', dataIndex: 'returnRate', key: 'returnRate' },
            { title: '비고', dataIndex: 'note', key: 'note' },
          ],
          data: [
            { key: '1', threshold: 85, trades: '0건', winRate: '-', returnRate: '-', note: '너무 엄격하여 기회를 모두 놓침' },
            { key: '2', threshold: 70, trades: '14건', winRate: '50.0%', returnRate: '+0.13%', note: '안정적 흐름, 채택' },
            { key: '3', threshold: 55, trades: '49건', winRate: '46.2%', returnRate: '-0.76%', note: '잦은 매매로 수수료 손실 발생' },
          ],
        },
      ],
      formulas: [
        '총점 = Σ(w_i × score_i) / Σ(w_i)',
        '진입 조건: total_score ≥ entry_score_threshold',
      ],
      highlights: [
        '가중치를 0으로 설정하면 해당 조건을 완전히 무시합니다. 가중치가 높을수록 해당 조건이 총점에 미치는 영향이 커집니다.',
      ],
    },
  },

  // ── Section 3: 매도/청산 규칙 ──
  {
    key: 'exit',
    title: '매도/청산 규칙',
    content: {
      paragraphs: [
        '수익을 지키고 손실을 최소화하기 위해 수학적 계산에 기반하여 기계적으로 매도합니다. 청산은 분할 익절, 동적 손절, 트레일링 스탑의 3단계 파이프라인으로 구성됩니다.',
        '분할 익절: 1차 목표가로 가격이 볼린저 밴드 중앙선(20일 이동평균선)에 도달하면 보유 수량의 50%를 매도하여 본전 수익을 확보합니다. 2차 목표가로 나머지 50%는 가격이 볼린저 밴드 상단선에 닿거나 상승세가 꺾이는 지표가 나타날 때 매도하여 추가 수익을 노립니다.',
        '동적 ATR 손절: 고정된 -3% 손절 대신, 최근 시장의 평균적인 흔들림 폭(ATR)을 계산하여 그 폭의 2.5배 이상 가격이 떨어지면 즉시 매도합니다. 시장이 평소보다 거칠게 숨을 쉰다면 손절 범위를 넓게 잡고, 시장이 조용하다면 좁게 잡아 불필요한 손절을 방지합니다.',
        '트레일링 스탑: 1차 익절 후 남은 물량에 대해 최고가 대비 ATR × 2.0 이상 하락하면 전량 매도합니다. 상승 추세에서 수익을 최대한 끌고 가면서도, 반전 시 빠르게 탈출하는 안전장치입니다.',
      ],
      tables: [
        {
          title: '청산 파이프라인',
          columns: [
            { title: '단계', dataIndex: 'stage', key: 'stage' },
            { title: '조건', dataIndex: 'condition', key: 'condition' },
            { title: '행동', dataIndex: 'action', key: 'action' },
          ],
          data: [
            { key: '1', stage: '1차 익절', condition: '가격 ≥ BB 중앙선 (20일 이동평균)', action: '보유 수량의 50% 매도' },
            { key: '2', stage: '2차 익절', condition: '가격 ≥ BB 상단선', action: '나머지 전량 매도' },
            { key: '3', stage: '동적 손절', condition: '가격 ≤ 매수가 - ATR × 2.5', action: '전량 즉시 매도' },
            { key: '4', stage: '트레일링 스탑', condition: '1차 익절 후, 최고가 대비 ATR × 2.0 하락', action: '남은 전량 매도' },
          ],
        },
      ],
      highlights: [
        '고정된 -3% 손절 대신, 최근 시장의 평균적인 흔들림 폭(ATR)을 계산하여 유연한 방어막을 설정합니다. 시장이 거칠면 손절 범위를 넓게, 조용하면 좁게 잡습니다.',
      ],
    },
  },

  // ── Section 4: 시장 레짐 ──
  {
    key: 'regime',
    title: '시장 레짐',
    content: {
      paragraphs: [
        '봇은 현재 시장 상태를 횡보, 추세, 변동성 폭발의 3가지 레짐으로 분류합니다. 레짐에 따라 진입 임계치를 동적으로 조정하여, 위험한 시장에서는 더 확실한 기회만 포착하고 안정적인 시장에서는 원래 기준대로 매매합니다.',
        '이전에는 추세/변동성 장세에서 매수를 완전히 차단했으나, 현재는 하이브리드 오프셋 시스템으로 임계치만 높여 진입 가능성을 열어둡니다. 비유하자면 파도가 높을 때 배를 아예 띄우지 않는 것이 아니라, 더 숙련된 선장만 출항할 수 있도록 기준을 높이는 것입니다.',
        '오프셋이 적용된 effective threshold의 상한은 99점으로 제한됩니다.',
      ],
      tables: [
        {
          title: '레짐 분류 및 진입 영향',
          columns: [
            { title: '레짐', dataIndex: 'regime', key: 'regime' },
            { title: '판정 기준', dataIndex: 'criteria', key: 'criteria' },
            { title: '진입 영향', dataIndex: 'effect', key: 'effect' },
          ],
          data: [
            { key: '1', regime: '횡보 (Ranging)', criteria: '기본 모드', effect: 'offset 0 (threshold 그대로)' },
            { key: '2', regime: '추세 (Trending)', criteria: 'BTC ADX ≥ 25', effect: 'offset +15 (기본값)' },
            { key: '3', regime: '변동성 폭발 (Volatile)', criteria: '변동성 비율 ≥ 2.0', effect: 'offset +25 (기본값)' },
          ],
        },
      ],
      formulas: [
        'effective_threshold = min(entry_score_threshold + regime_offset, 99)',
      ],
      highlights: [
        '이전에는 추세/변동성 장세에서 매수를 완전히 차단했으나, 현재는 임계치만 높여 \'더 확실한 기회\'만 포착합니다. 횡보장에서는 원래 임계치를 그대로 사용합니다.',
      ],
    },
  },

  // ── Section 5: 파라미터 상세 ──
  {
    key: 'params',
    title: '파라미터 상세',
    content: {
      paragraphs: [
        '파라미터 설정은 기술 지표의 모양과 수치 자체를 바꿉니다. 비유하자면 온도계의 단위를 섭씨에서 화씨로 바꾸거나, 눈금의 간격을 조정하는 것과 같습니다. 측정 도구 자체를 변경하는 단계입니다.',
        '각 파라미터 그룹이 지표 계산에 어떤 영향을 주는지 아래 표에서 확인할 수 있습니다.',
      ],
      tables: [
        {
          title: '볼린저 밴드 파라미터',
          columns: [
            { title: '파라미터', dataIndex: 'param', key: 'param' },
            { title: '기본값', dataIndex: 'defaultVal', key: 'defaultVal' },
            { title: '설명', dataIndex: 'description', key: 'description' },
          ],
          data: [
            { key: '1', param: 'bb_period', defaultVal: 20, description: '이동평균선을 계산하는 기간. 값이 클수록 밴드가 완만해진다.' },
            { key: '2', param: 'bb_std_dev', defaultVal: 2.0, description: '밴드의 폭을 결정하는 표준편차 배수. 값이 클수록 밴드가 넓어져 신호가 적게 발생한다.' },
          ],
        },
        {
          title: 'RSI 파라미터',
          columns: [
            { title: '파라미터', dataIndex: 'param', key: 'param' },
            { title: '기본값', dataIndex: 'defaultVal', key: 'defaultVal' },
            { title: '설명', dataIndex: 'description', key: 'description' },
          ],
          data: [
            { key: '1', param: 'rsi_period', defaultVal: 14, description: '상대강도지수를 계산하는 기간.' },
            { key: '2', param: 'rsi_oversold', defaultVal: 30, description: '과매도 구간을 정의하는 기준점.' },
          ],
        },
        {
          title: 'ATR 손절 파라미터',
          columns: [
            { title: '파라미터', dataIndex: 'param', key: 'param' },
            { title: '기본값', dataIndex: 'defaultVal', key: 'defaultVal' },
            { title: '설명', dataIndex: 'description', key: 'description' },
          ],
          data: [
            { key: '1', param: 'atr_period', defaultVal: 14, description: '변동성(ATR)을 계산하는 기간.' },
            { key: '2', param: 'atr_stop_multiplier', defaultVal: 2.5, description: 'ATR에 이 값을 곱해 손절 거리를 정한다. 값이 클수록 손절선이 멀어진다.' },
          ],
        },
        {
          title: '프리셋 비교',
          columns: [
            { title: '프리셋', dataIndex: 'preset', key: 'preset' },
            { title: '임계치', dataIndex: 'threshold', key: 'threshold' },
            { title: 'BB σ', dataIndex: 'bbStd', key: 'bbStd' },
            { title: '추세 오프셋', dataIndex: 'trendOffset', key: 'trendOffset' },
            { title: '변동성 오프셋', dataIndex: 'volOffset', key: 'volOffset' },
          ],
          data: [
            { key: '1', preset: '보수적', threshold: 90, bbStd: 2.5, trendOffset: 20, volOffset: 30 },
            { key: '2', preset: '공격적', threshold: 55, bbStd: 1.5, trendOffset: 5, volOffset: 10 },
            { key: '3', preset: '횡보장', threshold: 70, bbStd: 2.0, trendOffset: 15, volOffset: 25 },
            { key: '4', preset: '변동성 장세', threshold: 75, bbStd: 2.5, trendOffset: 10, volOffset: 15 },
          ],
        },
      ],
      highlights: [
        '파라미터 설정은 \'온도계의 눈금\'을 바꾸는 것이고, 매수 진입 조건은 \'에어컨 설정 온도\'를 바꾸는 것입니다.',
      ],
    },
  },

  // ── Section 6: 리스크 관리 ──
  {
    key: 'risk',
    title: '리스크 관리',
    content: {
      paragraphs: [
        '봇은 수학적으로 파산 확률을 최소화하도록 설계되었습니다. 과거 매매 기록(최근 30회 이상)의 승률과 손익비를 기반으로 켈리 공식(Kelly Criterion)을 적용하여 최적의 투입 비중을 계산하며, Half-Kelly 전략으로 계산된 비중의 50%만 사용하여 수익성을 유지하면서 파산 위험을 극도로 낮춥니다.',
        '매매 기록이 30회 미만인 초기 단계에서는 안전을 위해 고정 비중(20%)을 사용합니다. 또한 실제 매수 주문 직전에 호가창의 잔량을 확인하여 예상 슬리피지가 50bps(0.5%)를 초과하면 매매를 포기합니다.',
      ],
      tables: [
        {
          title: '리스크 관리 규칙',
          columns: [
            { title: '항목', dataIndex: 'rule', key: 'rule' },
            { title: '기준', dataIndex: 'value', key: 'value' },
          ],
          data: [
            { key: '1', rule: '종목당 최대 비중', value: '20%' },
            { key: '2', rule: '동시 운용 종목', value: '최대 5개' },
            { key: '3', rule: '일일 손실 한도', value: '전체 자산 대비 5%' },
            { key: '4', rule: '슬리피지 허용', value: '50bps (0.5%)' },
            { key: '5', rule: '매매 기록 부족 시', value: '고정 20% 비중 (30회 미만)' },
          ],
        },
      ],
      highlights: [
        '봇은 수학적으로 \'파산 확률\'을 최소화하도록 설계되었습니다. Half-Kelly 전략으로 최적 비중의 절반만 사용하여 수익성을 유지하면서 위험을 극도로 낮춥니다.',
      ],
    },
  },

  // ── Section 7: 실행 시점 ──
  {
    key: 'timing',
    title: '실행 시점과 데이터 기준',
    content: {
      paragraphs: [
        'Zenith는 틱(실시간 체결가) 이벤트가 들어올 때마다 즉시 신호를 내는 구조가 아닙니다. 오케스트레이터가 기본 10초 주기로 루프를 돌며 진입/청산을 평가합니다.',
        '각 평가 시점마다 업비트에서 15분봉 OHLCV를 다시 조회하고, 마지막 캔들의 close 값을 현재 가격으로 사용해 지표를 계산합니다. 즉, 루프는 10초마다 돌지만 신호의 기준 축은 15분봉입니다.',
        '이 방식은 노이즈에 과민반응하는 것을 줄이고, 수수료/슬리피지로 인한 과매매를 완화하기 위한 설계입니다. 전략 파라미터(BB/RSI/ATR, 임계치, 레짐 오프셋)도 15분봉 기준으로 검증되어 있습니다.',
      ],
      tables: [
        {
          title: '실행 타이밍 비교',
          columns: [
            { title: '항목', dataIndex: 'item', key: 'item' },
            { title: '현재 시스템', dataIndex: 'current', key: 'current' },
            { title: '틱 즉시 실행 시', dataIndex: 'tickMode', key: 'tickMode' },
          ],
          data: [
            { key: '1', item: '평가 주기', current: '10초 루프', tickMode: '틱 이벤트마다 즉시' },
            { key: '2', item: '가격 기준', current: '15분봉 마지막 close', tickMode: '실시간 체결가' },
            { key: '3', item: '신호 안정성', current: '상대적으로 안정적', tickMode: '노이즈 민감, 깜빡 신호 증가' },
            { key: '4', item: '거래 비용', current: '과매매 억제', tickMode: '거래 빈도 증가로 비용 확대 가능' },
            { key: '5', item: '전략 검증 일치성', current: '백테스트/튜닝 전제와 일치', tickMode: '전제 불일치로 재검증 필요' },
          ],
        },
      ],
      highlights: [
        '핵심은 "최신 데이터를 버린다"가 아니라, 최신 정보는 10초마다 반영하되 판단 기준은 15분봉으로 안정화해 과매매를 줄인다는 점입니다.',
      ],
    },
  },
];

/** 용어 사전 항목 */
export interface GuideGlossaryTerm {
  term: string;
  simple: string;
  detail: string;
}

/** 가이드 페이지 용어 사전 */
export const GUIDE_GLOSSARY: GuideGlossaryTerm[] = [
  { term: '평균 회귀', simple: '많이 벗어난 가격이 평균 쪽으로 돌아오려는 성질', detail: '가격이 급등·급락 후 원래 범위로 돌아오는 흐름을 노리는 전략 개념입니다.' },
  { term: '변동성', simple: '가격이 흔들리는 정도', detail: '같은 시간 동안 가격이 얼마나 크게 오르내리는지를 뜻합니다.' },
  { term: '레짐', simple: '현재 시장 상태(횡보/추세/변동성 폭발)', detail: '시장이 조용한지, 한 방향으로 강한지, 비정상적으로 흔들리는지를 분류한 상태값입니다.' },
  { term: '볼린저 밴드(BB)', simple: '평균선 위아래로 만든 가격 범위 밴드', detail: '가격이 보통 움직이는 범위를 시각화한 지표입니다. 하단 이탈·복귀 여부를 진입 판단에 씁니다.' },
  { term: 'RSI', simple: '최근 상승/하락 힘의 균형(0~100)', detail: '낮을수록 과매도, 높을수록 과매수로 해석하는 대표 지표입니다.' },
  { term: 'ATR', simple: '평균적인 가격 흔들림 폭', detail: '손절 거리와 트레일링 스탑 폭을 시장 상황에 맞게 조절할 때 사용합니다.' },
  { term: 'ADX', simple: '추세의 강도(방향 아님)', detail: '상승/하락 방향보다 추세가 강한지 약한지를 수치로 보여줍니다.' },
  { term: '임계값(Threshold)', simple: '매수/매도 실행 기준점', detail: '점수가 이 값 이상이면 신호를 실행합니다. 높을수록 보수적입니다.' },
  { term: '오프셋(Offset)', simple: '기준점에 더하는 추가 점수', detail: '시장 레짐이 위험하면 임계값에 가산해 진입을 더 어렵게 만드는 장치입니다.' },
  { term: '슬리피지', simple: '예상가와 실제 체결가의 차이', detail: '시장가 주문에서 호가 잔량 부족 등으로 생기는 체결 가격 미끄러짐입니다.' },
  { term: '켈리 비중', simple: '손익 통계로 계산한 권장 투자 비율', detail: '승률과 손익비를 바탕으로 자금 배분 비중을 계산하는 방법입니다. Zenith는 보수적으로 절반만 사용합니다.' },
  { term: '분할 익절', simple: '수익 구간에서 나눠서 매도', detail: '한 번에 전량 매도하지 않고 1차/2차로 나눠 리스크와 수익을 함께 관리합니다.' },
  { term: '트레일링 스탑', simple: '고점 대비 하락폭 기준 자동 매도', detail: '가격이 오른 뒤 되돌림이 커지면 남은 물량을 자동으로 정리하는 규칙입니다.' },
  { term: 'OHLCV', simple: '시가/고가/저가/종가/거래량', detail: '캔들 데이터를 구성하는 기본 5개 값으로 지표 계산의 입력이 됩니다.' },
];
