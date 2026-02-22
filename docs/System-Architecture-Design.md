# 시스템 아키텍처 설계서 (System Architecture Design)
**버전:** 1.1 (AntD UI 반영)
**작성일:** 2026-02-21

## 1. 시스템 개요
본 시스템은 업비트 API를 통해 데이터를 수집하고, Supabase를 데이터베이스로 활용하며, React와 AntD 기반의 대시보드로 현황을 모니터링하는 로컬 구동형 자동 매매 시스템입니다.

## 2. 기술 스택
- **Language:** Python 3.10+, JavaScript/TypeScript (React)
- **Frontend UI:** Ant Design (AntD)
- **Database:** Supabase (PostgreSQL)
- **Exchange API:** Upbit API
- **Notification:** KakaoTalk Messaging API
- **Deployment:** Local PC (Always-on)

## 3. 계층별 구조
### 3.1 데이터 수집부 (Data Collector)
- **Upbit API Interface:** REST API 및 WebSocket을 통한 실시간 데이터 수집.

### 3.2 전략 연산부 (Strategy Engine)
- **Mean Reversion Logic:** 볼린저 밴드 및 RSI 기반 알고리즘 연산.

### 3.3 주문 및 알림부 (Action Layer)
- **Order Executor:** 매매 주문 집행 및 KakaoTalk 알림 전송.

### 3.4 대시보드 UI (Frontend Layer) - *추가*
- **Monitoring Web:** React 및 AntD를 활용하여 자산 현황, 매매 로그, 전략 적합도를 시각화.

### 3.5 데이터 저장부 (Storage Layer)
- **Supabase DB:** 매매 기록, 일별 손익, 시스템 로그 영구 저장.

## 4. 데이터 흐름
1. [Upbit] -> 시세 데이터 수집 -> [Python Engine]
2. [Python Engine] -> 전략 연산 -> 매매 신호 생성
3. [Python Engine] -> [Upbit] 주문 전송 & [Supabase] 기록 저장
4. [Supabase] -> **[React/AntD Dashboard]** 실시간 데이터 시각화
5. [Python Engine] -> [KakaoTalk] 매매 결과 알림 전송