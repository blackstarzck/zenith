# Feature: 뉴스 즉시 표시 + AI 분석 중 UX

## 배경

현재 파이프라인은 뉴스 수집 → AI 분석 → DB 저장이 순차적이라 10건 분석에 10-50초 걸림.
사용자가 뉴스를 즉시 보고, AI 분석은 백그라운드에서 진행되는 2-phase 방식으로 변경.

## 핵심 접근법

`decision` 컬럼이 `TEXT DEFAULT 'WAIT'`이고 CHECK 제약이 없으므로, `'PENDING'` 값을 새로 사용하여
"AI 분석 중" 상태를 표현. 스키마 마이그레이션 불필요.

```
Phase 1: 뉴스 수집 → 즉시 INSERT (decision='PENDING', confidence=0)
  → 프론트엔드에 즉시 뉴스 카드 표시 ("AI 분석 중...")
Phase 2: Groq 분석 → UPDATE (decision='BUY'/'SELL'/etc, confidence=85, ...)
  → 프론트엔드에 분석 결과 실시간 반영
```

---

## TODO 목록

### TODO-1: 백엔드 — storage/client.py에 update_sentiment_insight 메서드 추가
- **파일**: `src/storage/client.py`
- **작업**: `insert_sentiment_insight()` 아래에 새 메서드 추가
- **위치**: L457 근처 (insert_sentiment_insight 메서드 바로 다음)

```python
    def update_sentiment_insight(self, news_id: str, analysis: dict[str, Any]) -> bool:
        """뉴스 감성 분석 결과를 업데이트합니다 (2-phase: 뉴스 먼저 저장 → 분석 후 업데이트)."""
        try:
            update_data = {
                "sentiment_score": analysis.get("sentiment_score", 0.0),
                "sentiment_label": analysis.get("sentiment_label", "neutral"),
                "decision": analysis.get("decision", "WAIT"),
                "confidence": analysis.get("confidence", 0.0),
                "reasoning_chain": analysis.get("reasoning_chain"),
                "keywords": analysis.get("keywords", []),
                "positive_factors": analysis.get("positive_factors", []),
                "negative_factors": analysis.get("negative_factors", []),
            }
            result = self._client.table("sentiment_insights").update(update_data).eq("news_id", news_id).execute()
            logger.info("감성 분석 업데이트: %s", news_id[:16])
            return bool(result.data)
        except Exception:
            logger.exception("감성 분석 업데이트 실패: %s", news_id)
            return False
```

- **참조 패턴**: 기존 `insert_sentiment_insight()` (L433-457)의 에러 핸들링 패턴 따름
- **QA**: 파일 읽어서 메서드 존재 확인, `update` + `eq("news_id")` 패턴 확인

### TODO-2: 백엔드 — orchestrator.py의 _run_sentiment_cycle 2-phase로 변경
- **파일**: `src/orchestrator.py`
- **작업**: `_run_sentiment_cycle()` (L941-979)를 2-phase로 리팩터

현재 로직 (L941-979):
```python
for news in news_list:
    analysis = self._sentiment_analyzer.analyze(...)  # 2-5초 대기
    insight = { news + analysis 합침 }
    self._storage.insert_sentiment_insight(insight)    # 분석 후에야 INSERT
```

변경 후:
```python
def _run_sentiment_cycle(self) -> None:
    """뉴스 수집 → 즉시 저장 → 감성 분석 → 업데이트 사이클을 실행합니다."""
    try:
        news_list = self._news_collector.fetch_latest_news(self._seen_news_ids)
        if not news_list:
            return

        # Phase 1: 뉴스 즉시 저장 (decision='PENDING')
        saved_news = []
        for news in news_list:
            try:
                row = {
                    "news_id": news["news_id"],
                    "title": news["title"],
                    "source": news["source"],
                    "url": news["url"],
                    "currencies": news["currencies"],
                    "decision": "PENDING",
                }
                self._storage.insert_sentiment_insight(row)
                self._seen_news_ids.add(news["news_id"])
                saved_news.append(news)
            except Exception as e:
                logger.error("뉴스 저장 실패 [%s]: %s", news.get("title", "?")[:30], e)

        if saved_news:
            logger.info("[감성 분석] %d건 뉴스 저장 완료, AI 분석 시작", len(saved_news))

        # Phase 2: AI 감성 분석 후 업데이트
        analyzed = 0
        for news in saved_news:
            try:
                analysis = self._sentiment_analyzer.analyze(
                    title=news["title"],
                    source=news["source"],
                    currencies=news["currencies"],
                )
                self._storage.update_sentiment_insight(news["news_id"], analysis)
                analyzed += 1
                time.sleep(1.0)  # Groq rate limit 방어
            except Exception as e:
                logger.error("감성 분석 실패 [%s]: %s", news.get("title", "?")[:30], e)

        if analyzed:
            logger.info("[감성 분석] %d건 AI 분석 완료", analyzed)

    except Exception:
        logger.warning("감성 분석 사이클 실패 — 다음 주기에 재시도")
```

- **핵심 변경점**:
  1. Phase 1에서 `decision='PENDING'`으로 즉시 INSERT → 프론트에 바로 표시
  2. Phase 2에서 `update_sentiment_insight()`로 분석 결과 UPDATE
  3. `_seen_news_ids.add()`를 Phase 1에서 수행 (중복 방지)
- **QA**: `_run_sentiment_cycle` 읽어서 2-phase 구조 확인, `PENDING` 사용 확인

### TODO-3: 프론트엔드 — database.ts 타입에 PENDING 추가
- **파일**: `frontend/src/types/database.ts`
- **작업**: L113의 `decision` 타입에 `'PENDING'` 추가

현재 (L113):
```typescript
  decision: 'BUY' | 'SELL' | 'HOLD' | 'WAIT';
```

변경 후:
```typescript
  decision: 'BUY' | 'SELL' | 'HOLD' | 'WAIT' | 'PENDING';
```

- **QA**: 타입 정의 읽어서 `PENDING` 존재 확인

### TODO-4: 프론트엔드 — useSupabase.ts에 UPDATE 이벤트 구독 추가
- **파일**: `frontend/src/hooks/useSupabase.ts`
- **작업**: `useSentimentInsights` 훅의 Realtime 구독에 UPDATE 이벤트 핸들러 추가

현재 (L582-591):
```typescript
    const channel = supabase
      .channel('sentiment-insights-realtime')
      .on(
        'postgres_changes',
        { event: 'INSERT', schema: 'public', table: 'sentiment_insights' },
        (payload) => {
          setInsights((prev) => [payload.new as SentimentInsight, ...prev].slice(0, limit));
        },
      )
      .subscribe();
```

변경 후:
```typescript
    const channel = supabase
      .channel('sentiment-insights-realtime')
      .on(
        'postgres_changes',
        { event: 'INSERT', schema: 'public', table: 'sentiment_insights' },
        (payload) => {
          setInsights((prev) => [payload.new as SentimentInsight, ...prev].slice(0, limit));
        },
      )
      .on(
        'postgres_changes',
        { event: 'UPDATE', schema: 'public', table: 'sentiment_insights' },
        (payload) => {
          setInsights((prev) =>
            prev.map((item) =>
              item.id === (payload.new as SentimentInsight).id
                ? (payload.new as SentimentInsight)
                : item,
            ),
          );
        },
      )
      .subscribe();
```

- **핵심**: UPDATE 시 기존 배열에서 같은 `id`를 찾아 교체 (불변 업데이트)
- **QA**: 훅 읽어서 `.on('postgres_changes', { event: 'UPDATE' ...})` 존재 확인

### TODO-5: 프론트엔드 — SentimentInsightPanel에 "AI 분석 중" 상태 UI 추가
- **파일**: `frontend/src/components/SentimentInsightPanel.tsx`
- **작업**: `decision === 'PENDING'`일 때 카드에 분석 중 UI 표시

**변경 1**: 상수 추가 (L23-28, DECISION_COLORS에 PENDING 추가):
```typescript
const DECISION_COLORS: Record<string, string> = {
  BUY: '#52c41a',
  SELL: '#ff4d4f',
  HOLD: '#faad14',
  WAIT: '#8c8c8c',
  PENDING: '#1890ff',
};
```

**변경 2**: 카드 헤더의 decision Tag 부분 (L138-143):
현재:
```tsx
<Tag color={DECISION_COLORS[insight.decision] || '#8c8c8c'} style={{ margin: 0, fontWeight: 600, border: 'none' }}>
  {insight.decision}
</Tag>
```

변경 후:
```tsx
<Tag
  color={DECISION_COLORS[insight.decision] || '#8c8c8c'}
  style={{ margin: 0, fontWeight: 600, border: 'none' }}
  icon={insight.decision === 'PENDING' ? <Spin size="small" style={{ marginRight: 4 }} /> : undefined}
>
  {insight.decision === 'PENDING' ? 'AI 분석 중' : insight.decision}
</Tag>
```

**변경 3**: PENDING일 때 감성 바 + 키워드 영역 숨김 (L146-182):
감성 바와 키워드는 `insight.decision !== 'PENDING'`일 때만 렌더.
```tsx
{insight.decision !== 'PENDING' && (
  <>
    {/* 감성 바 */}
    <div style={{ marginBottom: 12 }}>
      ...existing bar code...
    </div>

    {/* 키워드 칩 */}
    <div style={{ ... }}>
      ...existing keyword code...
    </div>
  </>
)}
```

- **참조**: 기존 프로젝트 인라인 스타일 컨벤션 (`style={{}}`)
- **QA**: 브라우저에서 PENDING 상태 카드가 스피너 + "AI 분석 중" 텍스트 표시 확인

### TODO-6: 커밋
- 변경된 파일 4개 스테이징:
  1. `src/storage/client.py`
  2. `src/orchestrator.py`
  3. `frontend/src/types/database.ts`
  4. `frontend/src/hooks/useSupabase.ts`
  5. `frontend/src/components/SentimentInsightPanel.tsx`
- 커밋 메시지: `feat: 뉴스 즉시 표시 + AI 분석 중 UX — 2-phase insert/update 파이프라인`

## 영향 범위

- `src/storage/client.py` — `update_sentiment_insight()` 메서드 추가
- `src/orchestrator.py` — `_run_sentiment_cycle()` 2-phase 리팩터
- `frontend/src/types/database.ts` — `decision` 타입에 `'PENDING'` 추가
- `frontend/src/hooks/useSupabase.ts` — Realtime UPDATE 구독 추가
- `frontend/src/components/SentimentInsightPanel.tsx` — PENDING 상태 UI

**스키마 변경 없음** — `decision` 컬럼이 TEXT 타입이라 `'PENDING'` 값 자연 수용.

## Final Verification Wave

- [ ] `storage/client.py`에 `update_sentiment_insight` 메서드 존재
- [ ] `orchestrator.py`의 `_run_sentiment_cycle`이 2-phase 구조 (INSERT→UPDATE)
- [ ] `database.ts`의 `decision` 타입에 `'PENDING'` 포함
- [ ] `useSupabase.ts`에 `event: 'UPDATE'` 구독 존재
- [ ] `SentimentInsightPanel.tsx`에서 `PENDING` 상태일 때 "AI 분석 중" UI 표시
- [ ] 커밋 완료
