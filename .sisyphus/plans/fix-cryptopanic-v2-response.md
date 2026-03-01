# Fix: CryptoPanic v2 응답 구조 불일치 — 뉴스 수집 0건

## 배경

이전 계획(fix-sentiment-insights-401)에서 엔드포인트를 v1→v2로 수정했으나,
v2 API의 **응답 JSON 구조**가 v1과 완전히 다름. 결과적으로 모든 뉴스가 스킵됨.

## 근본 원인

CryptoPanic Developer v2 API 응답에 `id`, `url`, `source`, `currencies` 필드가 없음:

| 필드 | v1 (코드 기대) | v2 (실제 응답) |
|---|---|---|
| `id` | ✅ 정수 ID | ❌ **없음** → `news_id=""` → `continue`로 스킵 |
| `url` | ✅ 원문 링크 | ❌ 없음 |
| `source` | ✅ `{title: "CoinDesk"}` | ❌ 없음 |
| `currencies` | ✅ `[{code: "BTC"}]` | ❌ 없음 |
| `title` | ✅ | ✅ |
| `description` | ❌ | ✅ (신규) |
| `published_at` | ❌ | ✅ |
| `created_at` | ✅ | ✅ |
| `kind` | ✅ | ✅ |

실제 API 응답 (curl 검증 완료):
```json
{"next":null,"previous":null,"results":[
  {"title":"일론 머스크의 회사...","description":"...","published_at":"2026-02-28T13:36:08Z","created_at":"2026-02-28T13:36:08+00:00","kind":"news"}
]}
```

## TODO 목록

### TODO-1: news_collector.py v2 응답 구조 대응 수정
- **파일**: `src/collector/news_collector.py`
- **작업**: v2 API 응답 구조에 맞게 파싱 로직 전면 수정

#### 변경 상세:

**1. import 추가** (L1-5):
```python
from __future__ import annotations

import hashlib
import logging
import time
from typing import TYPE_CHECKING, Any
```

**2. params에서 `public` 제거** (L45-50):
v2 Developer API에서 `public=true`는 필드를 제한하는 파라미터임. 제거해야 풀 데이터 반환.
단, curl 테스트 결과 `public` 유무 관계없이 v2는 id/url/source/currencies를 반환하지 않음.
따라서 `public` 유지/제거는 무관 — 파싱 로직 수정이 핵심.
```python
        params = {
            "auth_token": self._api_key,
            "currencies": self._currencies,
            "regions": "ko",
        }
```

**3. 결과 파싱 로직 수정** (L62-84):
기존 v1 필드 의존 코드를 v2 구조에 맞게 수정:
```python
            for result in results:
                title = result.get("title", "")
                created_at = result.get("created_at", result.get("published_at", ""))

                # v2 API는 id 필드를 제공하지 않음 → title+created_at 해시로 고유 ID 생성
                raw_id = f"{title}:{created_at}"
                news_id = hashlib.sha256(raw_id.encode()).hexdigest()[:16]

                if not title or news_id in seen_ids:
                    continue

                # v2 API는 source/url/currencies 필드를 제공하지 않음
                # currencies는 요청 파라미터에서 가져옴
                news_item = {
                    "news_id": news_id,
                    "title": title,
                    "source": "CryptoPanic",
                    "url": "",
                    "currencies": [c.strip() for c in self._currencies.split(",") if c.strip()],
                    "created_at": created_at,
                }
                news_list.append(news_item)

                if len(news_list) >= self._max_news:
                    break
```

- **핵심 변경점**:
  1. `hashlib` import 추가
  2. `news_id`: `result.get("id")` → `hashlib.sha256(title+created_at).hexdigest()[:16]`
  3. `source`: `result.get("source", {}).get("title")` → `"CryptoPanic"` 고정
  4. `url`: `result.get("url")` → `""` (v2에서 미제공)
  5. `currencies`: `result.get("currencies")` → `self._currencies.split(",")` (요청 파라미터에서 가져옴)
  6. `public` 파라미터 제거 (불필요)

- **QA**:
  1. 파일 읽어서 `hashlib` import 존재 확인
  2. `result.get("id"` 패턴이 없어야 함
  3. `result.get("source"` 패턴이 없어야 함
  4. `result.get("currencies"` 패턴이 없어야 함
  5. `result.get("url"` 패턴이 없어야 함
  6. `hashlib.sha256` 사용 확인
  7. `"public"` 파라미터가 params dict에 없어야 함

### TODO-2: 수정 후 커밋
- `git add src/collector/news_collector.py && git commit -m "fix: CryptoPanic v2 응답 구조 대응 — news_id 해시 생성, 미제공 필드 폴백"`

## 영향 범위

- `src/collector/news_collector.py` — 1개 파일만 수정
- 다른 파일 변경 없음

## Final Verification Wave

- [ ] `news_collector.py`에 `hashlib` import 존재
- [ ] `result.get("id"` 패턴 없음
- [ ] `"public"` 파라미터 없음
- [ ] 파싱 로직이 v2 응답 구조(title, description, published_at, created_at, kind)에 대응
- [ ] 커밋 완료
