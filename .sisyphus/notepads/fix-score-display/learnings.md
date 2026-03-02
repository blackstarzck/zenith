- Added 'ERROR' decision handling to getEntryDecisionLabel in DashboardPage.tsx to match backend changes.
## 2026-03-02: 스코어 계산 로직 예외 격리
- 의  메서드 내 스코어 계산 및 게이트 체크 로직을 inner 로 감싸서 예외 발생 시에도 폴백값을 제공하도록 수정함.
- 이를 통해 특정 종목의 스코어 계산 실패가 전체 루프에 영향을 주지 않고, 프론트엔드 대시보드에서 '-' 대신 'ERROR' 상태와 오류 메시지를 표시할 수 있게 됨.
- 는 API rate limit 준수를 위해 inner  바깥에 유지함.
## 2026-03-02: 스코어 계산 로직 예외 격리
- src/orchestrator.py의 _evaluate_entries() 메서드 내 스코어 계산 및 게이트 체크 로직을 inner try/except로 감싸서 예외 발생 시에도 폴백값을 제공하도록 수정함.
- 이를 통해 특정 종목의 스코어 계산 실패가 전체 루프에 영향을 주지 않고, 프론트엔드 대시보드에서 '-' 대신 'ERROR' 상태와 오류 메시지를 표시할 수 있게 됨.
- time.sleep(0.2)는 API rate limit 준수를 위해 inner try/except 바깥에 유지함.
