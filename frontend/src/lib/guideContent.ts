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

/** 가이드 페이지 6개 섹션 콘텐츠 */
export const GUIDE_SECTIONS: GuideSection[] = [
  // ── Section 1: 전략 개요 ──
  {
    key: 'overview',
    title: '전략 개요',
    content: {
      paragraphs: [
        'Zenith의 핵심 전략은 "확증 기반 변동성 조절형 평균 회귀"입니다. 가격이 통계적 정상 범위를 벗어났을 때 평균으로 회귀하려는 성질을 이용하되, 추세가 완전히 무너지는 상황을 회피하기 위해 진입 확증과 동적 위험 관리를 결합한 알고리즘입니다.',
        '전략 설정은 크게 두 부분으로 나뉩니다. 상단 섹션은 기술 지표를 계산하는 방식을 결정하고, 하단 섹션은 계산된 지표를 바탕으로 실제 매수 여부를 결정하는 논리를 제어합니다. 비유하자면 상단은 "온도계의 눈금을 조정"하는 것이고, 하단은 "에어컨 설정 온도를 변경"하는 것입니다.',
        '파라미터 설정(상단)을 바꾸면 지표 수치 자체가 달라집니다. 예를 들어 rsi_period를 14에서 7로 줄이면 RSI 수치 자체가 변합니다. 반면 매수 진입 조건(하단)을 바꾸면 같은 지표 수치를 보는 눈높이와 기준점이 달라집니다.',
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
        '가격이 단순히 낮아졌다고 매수하는 것이 아니라, 하락세가 멈추고 반등의 에너지가 모이는 시점을 포착합니다. 기존의 엄격한 필터 방식(AND-gate) 대신, 여러 지표의 상태를 점수화하여 종합적으로 판단하는 스코어링 시스템을 사용합니다.',
        '봇은 6가지 항목에 대해 각각 0~100점의 점수를 매기고, 가중치를 곱한 합산 점수가 임계치를 넘으면 매수합니다. 비유하자면 시험 과목별 배점과 합격 커트라인을 정하는 것과 같습니다. 특정 지표가 기준에 약간 미달하더라도 다른 지표가 매우 강력한 신호를 보낸다면 진입이 가능해져, 유연한 대응이 가능합니다.',
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
];
