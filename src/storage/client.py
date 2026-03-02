"""
Supabase 스토리지 모듈.
매매 이력, 일별 통계, 시스템 로그, 봇 상태, 가격 스냅샷을 Supabase(PostgreSQL)에 저장합니다.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any

from supabase import create_client, Client
from supabase.lib.client_options import SyncClientOptions

from src.config import SupabaseConfig

logger = logging.getLogger(__name__)


class StorageClient:
    """Supabase DB 클라이언트 — 동기 방식.

    안정성 개선:
    - insert_trade(), upsert_daily_stats(), get_trades() 에 try/except 추가
    - DB 장애 시에도 봇 프로세스가 죽지 않도록 보호
    """

    def __init__(self, config: SupabaseConfig) -> None:
        if not config.url or not config.secret_key:
            raise ValueError("SUPABASE_URL 및 SUPABASE_SECRET_KEY가 필요합니다.")
        options = SyncClientOptions(
            postgrest_client_timeout=30,
            storage_client_timeout=30,
        )
        self._client: Client = create_client(config.url, config.secret_key, options)

    # ── trades ───────────────────────────────────────────────

    def insert_trade(
        self,
        symbol: str,
        side: str,
        price: float,
        volume: float,
        amount: float,
        fee: float,
        pnl: float | None = None,
        remaining_volume: float | None = None,
        reason: str | None = None,
        slippage: float | None = None,
    ) -> dict[str, Any]:
        """매매 체결 내역을 기록합니다."""
        row = {
            "symbol": symbol,
            "side": side,
            "price": price,
            "volume": volume,
            "amount": amount,
            "fee": fee,
            "created_at": datetime.utcnow().isoformat(),
        }
        if pnl is not None:
            row["pnl"] = pnl
        if remaining_volume is not None:
            row["remaining_volume"] = remaining_volume
        if reason is not None:
            row["reason"] = reason
        if slippage is not None:
            row["slippage"] = round(slippage, 4)

        try:
            result = self._client.table("trades").insert(row).execute()
            logger.info("Trade recorded: %s %s @ %s", side, symbol, price)
            return result.data[0] if result.data else {}
        except Exception:
            logger.exception("거래 기록 저장 실패: %s %s", side, symbol)
            return {}

    def get_trades(
        self,
        symbol: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """최근 매매 이력을 조회합니다."""
        try:
            query = self._client.table("trades").select("*").order("created_at", desc=True).limit(limit)
            if symbol:
                query = query.eq("symbol", symbol)
            result = query.execute()
            return result.data or []
        except Exception:
            logger.exception("거래 이력 조회 실패")
            return []
    def get_recent_sell_trades(self, limit: int = 100) -> list[dict]:
        """켈리 공식 계산용 최근 매도 거래 PnL 목록을 반환합니다.
    
        Returns:
            list[dict]: 각 dict에 'pnl' 키 포함. 빈 리스트면 데이터 없음.
        """
        try:
            result = (
                self._client.table("trades")
                .select("pnl")
                .eq("side", "ask")
                .not_.is_("pnl", "null")
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            return result.data or []
        except Exception as e:
            logger.exception("매도 거래 조회 실패: %s", e)
            return []


    # ── daily_stats ──────────────────────────────────────────

    def upsert_daily_stats(
        self,
        stats_date: "date",
        total_balance: float,
        net_profit: float,
        drawdown: float,
    ) -> dict[str, Any]:
        """일별 성과 지표를 갱신합니다 (upsert)."""
        row = {
            "stats_date": stats_date.isoformat(),
            "total_balance": total_balance,
            "net_profit": net_profit,
            "drawdown": drawdown,
        }
        try:
            result = (
                self._client.table("daily_stats")
                .upsert(row, on_conflict="stats_date")
                .execute()
            )
            logger.info("Daily stats upserted for %s", stats_date)
            return result.data[0] if result.data else {}
        except Exception:
            logger.exception("일일 통계 저장 실패: %s", stats_date)
            return {}

    def get_daily_stats(self, days: int = 30) -> list[dict[str, Any]]:
        """최근 N일간 성과 지표를 조회합니다."""
        try:
            result = (
                self._client.table("daily_stats")
                .select("*")
                .order("stats_date", desc=True)
                .limit(days)
                .execute()
            )
            return result.data or []
        except Exception:
            logger.exception("일일 통계 조회 실패")
            return []

    # ── balance_snapshots ────────────────────────────────────

    def insert_balance_snapshot(self, total_balance: float) -> None:
        """시간단위 자산 스냅샷을 저장합니다."""
        row = {
            "total_balance": total_balance,
            "created_at": datetime.utcnow().isoformat(),
        }
        try:
            self._client.table("balance_snapshots").insert(row).execute()
        except Exception:
            logger.exception("Failed to insert balance snapshot")

    def cleanup_old_balance_snapshots(self, days: int = 7) -> None:
        """N일 이전의 자산 스냅샷을 삭제합니다."""
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        try:
            self._client.table("balance_snapshots").delete().lt("created_at", cutoff).execute()
        except Exception:
            logger.exception("Failed to cleanup old balance snapshots")

    # ── system_logs ──────────────────────────────────────────

    def insert_log(self, level: str, message: str) -> None:
        """시스템 로그를 기록합니다."""
        row = {
            "level": level,
            "message": message,
            "created_at": datetime.utcnow().isoformat(),
        }
        try:
            self._client.table("system_logs").insert(row).execute()
        except Exception:
            # 로그 저장 실패가 시스템 전체를 중단시키면 안 됨
            logger.exception("Failed to insert system log")

    def get_recent_logs(self, limit: int = 20) -> list[dict[str, Any]]:
        """최근 시스템 로그를 조회합니다."""
        try:
            result = (
                self._client.table("system_logs")
                .select("*")
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            return result.data or []
        except Exception:
            logger.exception("시스템 로그 조회 실패")
            return []

    # ── bot_state (단일 행) ───────────────────────────────────

    def upsert_bot_state(
        self,
        *,
        initial_balance: float | None = None,
        current_balance: float | None = None,
        krw_balance: float | None = None,
        top_symbols: list[str] | None = None,
        symbol_volatilities: dict[str, dict] | None = None,
        is_active: bool | None = None,
        upbit_status: str | None = None,
        kakao_status: str | None = None,
        strategy_params: dict | None = None,
        market_regime: str | None = None,
        kelly_fraction: float | None = None,
    ) -> None:
        """봇 실시간 상태를 갱신합니다 (단일 행 upsert).

        전달된 필드만 업데이트합니다.
        """
        row: dict[str, Any] = {
            "id": 1,
            "updated_at": datetime.utcnow().isoformat() + "Z",
        }
        if initial_balance is not None:
            row["initial_balance"] = initial_balance
        if current_balance is not None:
            row["current_balance"] = current_balance
        if krw_balance is not None:
            row["krw_balance"] = krw_balance
        if top_symbols is not None:
            row["top_symbols"] = top_symbols
        if symbol_volatilities is not None:
            row["symbol_volatilities"] = symbol_volatilities
        if is_active is not None:
            row["is_active"] = is_active
        if upbit_status is not None:
            row["upbit_status"] = upbit_status
        if kakao_status is not None:
            row["kakao_status"] = kakao_status
        if strategy_params is not None:
            row["strategy_params"] = strategy_params
        if market_regime is not None:
            row["market_regime"] = market_regime
        if kelly_fraction is not None:
            row["kelly_fraction"] = round(kelly_fraction, 6)
        try:
            self._client.table("bot_state").upsert(
                row, on_conflict="id"
            ).execute()
        except Exception:
            logger.exception("봇 상태 저장 실패")

    def get_bot_state(self) -> dict[str, Any] | None:
        """현재 봇 상태를 조회합니다."""
        try:
            result = (
                self._client.table("bot_state")
                .select("*")
                .eq("id", 1)
                .limit(1)
                .execute()
            )
            return result.data[0] if result.data else None
        except Exception:
            logger.exception("봇 상태 조회 실패")
            return None

    def get_strategy_params(self) -> dict | None:
        """bot_state에서 strategy_params를 조회합니다.

        Returns:
            전략 파라미터 딕셔너리 (미설정 시 None)
        """
        state = self.get_bot_state()
        if state and state.get("strategy_params"):
            return state["strategy_params"]
        return None

    def save_strategy_params(self, params_dict: dict) -> None:
        """전략 파라미터를 bot_state에 저장합니다."""
        self.upsert_bot_state(strategy_params=params_dict)

    # ── kakao_tokens ─────────────────────────────────────────

    def get_kakao_tokens(self) -> dict[str, Any] | None:
        """저장된 카카오 토큰을 조회합니다."""
        try:
            result = (
                self._client.table("kakao_tokens")
                .select("*")
                .eq("id", 1)
                .limit(1)
                .execute()
            )
            return result.data[0] if result.data else None
        except Exception:
            logger.exception("카카오 토큰 조회 실패")
            return None

    def upsert_kakao_tokens(
        self,
        access_token: str,
        refresh_token: str,
    ) -> None:
        """카카오 토큰을 저장/갱신합니다."""
        row = {
            "id": 1,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "updated_at": datetime.utcnow().isoformat(),
        }
        try:
            self._client.table("kakao_tokens").upsert(
                row, on_conflict="id"
            ).execute()
            logger.info("카카오 토큰 갱신 저장 완료")
        except Exception:
            logger.exception("카카오 토큰 저장 실패")

    # ── price_snapshots ──────────────────────────────────────

    def insert_price_snapshot(
        self,
        symbol: str,
        price: float,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> None:
        """가격 스냅샷을 기록합니다 (차트 시각화용)."""
        row: dict[str, Any] = {
            "symbol": symbol,
            "price": price,
            "created_at": datetime.utcnow().isoformat(),
        }
        if stop_loss is not None:
            row["stop_loss"] = stop_loss
        if take_profit is not None:
            row["take_profit"] = take_profit
        try:
            self._client.table("price_snapshots").insert(row).execute()
        except Exception:
            logger.exception("가격 스냅샷 저장 실패: %s", symbol)

    def cleanup_old_snapshots(self, days: int = 7) -> None:
        """오래된 가격 스냅샷을 정리합니다."""
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        try:
            self._client.table("price_snapshots").delete().lt(
                "created_at", cutoff
            ).execute()
            logger.info("price_snapshots %d일 이전 데이터 정리 완료", days)
        except Exception:
            logger.exception("가격 스냅샷 정리 실패")

    # ── daily_reports ─────────────────────────────────────────

    def upsert_daily_report(
        self,
        report_date: "date",
        content: str,
        total_balance: float = 0.0,
        net_profit: float = 0.0,
        trade_count: int = 0,
        win_count: int = 0,
        loss_count: int = 0,
    ) -> dict[str, Any]:
        """일일 분석 리포트를 저장/갱신합니다 (upsert)."""
        row = {
            "report_date": report_date.isoformat(),
            "content": content,
            "total_balance": total_balance,
            "net_profit": net_profit,
            "trade_count": trade_count,
            "win_count": win_count,
            "loss_count": loss_count,
            "created_at": datetime.utcnow().isoformat(),
        }
        try:
            result = (
                self._client.table("daily_reports")
                .upsert(row, on_conflict="report_date")
                .execute()
            )
            logger.info("일일 리포트 저장 완료: %s", report_date)
            return result.data[0] if result.data else {}
        except Exception:
            logger.exception("일일 리포트 저장 실패: %s", report_date)
            return {}

    def get_daily_reports(self, limit: int = 30) -> list[dict[str, Any]]:
        """최근 일일 리포트 목록을 조회합니다."""
        try:
            result = (
                self._client.table("daily_reports")
                .select("id, report_date, total_balance, net_profit, trade_count, win_count, loss_count, created_at")
                .order("report_date", desc=True)
                .limit(limit)
                .execute()
            )
            return result.data or []
        except Exception:
            logger.exception("일일 리포트 목록 조회 실패")
            return []

    def get_daily_report(self, report_date: "date") -> dict[str, Any] | None:
        """특정 날짜의 일일 리포트(본문 포함)를 조회합니다."""
        try:
            result = (
                self._client.table("daily_reports")
                .select("*")
                .eq("report_date", report_date.isoformat())
                .limit(1)
                .execute()
            )
            return result.data[0] if result.data else None
        except Exception:
            logger.exception("일일 리포트 조회 실패: %s", report_date)
            return None

    # ── sentiment_insights ────────────────────────────────────

    def insert_sentiment_insight(self, data: dict[str, Any]) -> dict[str, Any]:
        """뉴스 감성 분석 결과를 저장합니다."""
        try:
            row = {
                "news_id": data["news_id"],
                "title": data["title"],
                "source": data.get("source"),
                "url": data.get("url"),
                "currencies": data.get("currencies", []),
                "sentiment_score": data.get("sentiment_score", 0.0),
                "sentiment_label": data.get("sentiment_label", "neutral"),
                "decision": data.get("decision", "WAIT"),
                "confidence": data.get("confidence", 0.0),
                "reasoning_chain": data.get("reasoning_chain"),
                "keywords": data.get("keywords", []),
                "positive_factors": data.get("positive_factors", []),
                "negative_factors": data.get("negative_factors", []),
                "volume_impact": data.get("volume_impact", False),
                "verification_horizon_min": data.get("verification_horizon_min"),
                "baseline_price": data.get("baseline_price"),
                "pending_reason": data.get("pending_reason"),
            }
            result = self._client.table("sentiment_insights").insert(row).execute()
            logger.info("감성 분석 저장: %s", data.get("title", "")[:50])
            return result.data[0] if result.data else {}
        except Exception:
            logger.exception("감성 분석 결과 저장 실패: %s", data.get("news_id", "?"))
            return {}
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
                "verification_horizon_min": analysis.get("verification_horizon_min"),
                "pending_reason": analysis.get("pending_reason"),
            }
            result = self._client.table("sentiment_insights").update(update_data).eq("news_id", news_id).execute()
            logger.info("감성 분석 업데이트: %s", news_id[:16])
            return bool(result.data)
        except Exception:
            logger.exception("감성 분석 업데이트 실패: %s", news_id)
            return False

    def get_recent_sentiment_insights(self, limit: int = 20) -> list[dict[str, Any]]:
        """최근 감성 분석 결과를 조회합니다."""
        try:
            result = (
                self._client.table("sentiment_insights")
                .select("*")
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            return result.data or []
        except Exception:
            logger.exception("감성 분석 결과 조회 실패")
            return []

    def cleanup_old_sentiment_insights(self, days: int = 7) -> None:
        """오래된 감성 분석 결과를 정리합니다."""
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        try:
            self._client.table("sentiment_insights").delete().lt("created_at", cutoff).execute()
            logger.info("sentiment_insights %d일 이전 데이터 정리 완료", days)
        except Exception:
            logger.exception("오래된 감성 분석 데이터 정리 실패")

    # ── 감성 검증 확장 메서드 ─────────────────────────────────

    def get_pending_sentiment_insights(self, limit: int = 200) -> list[dict[str, Any]]:
        """검증 대기 중인(verification_result IS NULL, decision != 'PENDING') 감성 분석 결과를 조회합니다."""
        try:
            result = (
                self._client.table("sentiment_insights")
                .select("*")
                .is_("verification_result", "null")
                .neq("decision", "PENDING")
                .order("created_at", desc=False)
                .limit(limit)
                .execute()
            )
            return result.data or []
        except Exception:
            logger.exception("검증 대기 감성 분석 조회 실패")
            return []

    def get_sentiment_insights_for_backfill(
        self,
        limit: int = 1000,
        days: int = 30,
        include_verified: bool = False,
        news_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """백필 대상 감성 분석 결과를 조회합니다.

        기본값은 미검증(verification_result IS NULL)만 조회합니다.
        include_verified=True면 이미 검증된 건도 포함해 재계산할 수 있습니다.
        """
        try:
            cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
            query = (
                self._client.table("sentiment_insights")
                .select("*")
                .neq("decision", "PENDING")
                .gte("created_at", cutoff)
                .order("created_at", desc=False)
                .limit(limit)
            )
            if not include_verified:
                query = query.is_("verification_result", "null")

            if news_ids:
                target_news_ids = [str(n).strip() for n in news_ids if str(n).strip()]
                if target_news_ids:
                    query = query.in_("news_id", target_news_ids)

            result = query.execute()
            return result.data or []
        except Exception:
            logger.exception("백필 대상 감성 분석 조회 실패")
            return []

    def finalize_sentiment_verification(
        self,
        *,
        news_id: str,
        actual_price_change: float,
        evaluation_price: float,
        verification_result: str,
        direction_match: bool | None,
        baseline_price: float,
        verification_window_start_at: datetime,
        verification_window_end_at: datetime,
        window_open_price: float,
        window_close_price: float,
        window_high_price: float,
        window_low_price: float,
        window_return_pct: float,
        window_max_rise_pct: float,
        window_max_drop_pct: float,
        verification_explanation: str,
        analysis_insight: str,
        evaluated_at: datetime,
        verification_horizon_min: int | None = None,
        pending_reason: str | None = None,
    ) -> bool:
        """감성 분석 검증 결과를 최종 기록합니다."""
        try:
            update_data: dict[str, Any] = {
                "actual_price_change": round(actual_price_change, 6),
                "evaluation_price": evaluation_price,
                "verification_result": verification_result,
                "direction_match": direction_match,
                "baseline_price": baseline_price,
                "verification_window_start_at": verification_window_start_at.isoformat(),
                "verification_window_end_at": verification_window_end_at.isoformat(),
                "window_open_price": window_open_price,
                "window_close_price": window_close_price,
                "window_high_price": window_high_price,
                "window_low_price": window_low_price,
                "window_return_pct": round(window_return_pct, 6),
                "window_max_rise_pct": round(window_max_rise_pct, 6),
                "window_max_drop_pct": round(window_max_drop_pct, 6),
                "verification_explanation": verification_explanation,
                "analysis_insight": analysis_insight,
                "evaluated_at": evaluated_at.isoformat(),
                "pending_reason": pending_reason,
            }
            if verification_horizon_min is not None:
                update_data["verification_horizon_min"] = int(verification_horizon_min)
            result = (
                self._client.table("sentiment_insights")
                .update(update_data)
                .eq("news_id", news_id)
                .execute()
            )
            return bool(result.data)
        except Exception:
            logger.exception("감성 검증 결과 저장 실패: %s", news_id)
            return False

    def update_sentiment_pending_reason(self, news_id: str, reason: str) -> None:
        """감성 분석 레코드의 대기 사유를 업데이트합니다."""
        try:
            self._client.table("sentiment_insights").update(
                {"pending_reason": reason}
            ).eq("news_id", news_id).execute()
        except Exception:
            logger.exception("대기 사유 업데이트 실패: %s", news_id)

    def rebuild_sentiment_performance_daily(self, target_date: date) -> None:
        """특정 날짜의 감성 검증 일일 집계를 재생성합니다."""
        try:
            # 해당 날짜의 검증 완료 데이터 조회
            start = datetime.combine(target_date, datetime.min.time()).isoformat()
            end = datetime.combine(target_date + timedelta(days=1), datetime.min.time()).isoformat()
            result = (
                self._client.table("sentiment_insights")
                .select("currencies, decision, verification_result, confidence, actual_price_change")
                .not_.is_("verification_result", "null")
                .gte("created_at", start)
                .lt("created_at", end)
                .execute()
            )
            rows = result.data or []
            if not rows:
                return

            # (currency, decision) 별 집계
            stats: dict[tuple[str, str], dict[str, Any]] = defaultdict(lambda: {
                "total": 0, "verified": 0, "correct": 0, "incorrect": 0,
                "conf_sum": 0.0, "change_sum": 0.0,
            })

            for row in rows:
                decision = str(row.get("decision", "WAIT")).upper()
                vr = row.get("verification_result")
                conf = float(row.get("confidence") or 0)
                change = float(row.get("actual_price_change") or 0)
                currencies = row.get("currencies") or []

                keys = [("ALL", decision), ("ALL", "ALL")]
                for cur in currencies:
                    keys.append((str(cur).upper(), decision))
                    keys.append((str(cur).upper(), "ALL"))

                for key in keys:
                    s = stats[key]
                    s["total"] += 1
                    if vr == "correct":
                        s["verified"] += 1
                        s["conf_sum"] += conf
                        s["change_sum"] += abs(change)
                        s["correct"] += 1
                    elif vr == "incorrect":
                        s["verified"] += 1
                        s["conf_sum"] += conf
                        s["change_sum"] += abs(change)
                        s["incorrect"] += 1

            # 기존 해당 날짜 집계 삭제 후 재삽입
            self._client.table("sentiment_performance_daily").delete().eq(
                "stats_date", target_date.isoformat()
            ).execute()

            insert_rows = []
            for (currency, decision), s in stats.items():
                insert_rows.append({
                    "stats_date": target_date.isoformat(),
                    "currency": currency,
                    "decision": decision,
                    "total_count": s["total"],
                    "verified_count": s["verified"],
                    "correct_count": s["correct"],
                    "incorrect_count": s["incorrect"],
                    "avg_confidence": round(s["conf_sum"] / s["verified"], 2) if s["verified"] > 0 else None,
                    "avg_actual_change": round(s["change_sum"] / s["verified"], 6) if s["verified"] > 0 else None,
                })

            if insert_rows:
                try:
                    self._client.table("sentiment_performance_daily").insert(insert_rows).execute()
                except Exception as e:
                    # 구버전 스키마( avg_actual_change 컬럼 없음 ) 호환 폴백
                    if "avg_actual_change" not in str(e):
                        raise
                    legacy_rows = [
                        {k: v for k, v in row.items() if k != "avg_actual_change"}
                        for row in insert_rows
                    ]
                    try:
                        self._client.table("sentiment_performance_daily").insert(legacy_rows).execute()
                        logger.warning(
                            "sentiment_performance_daily에 avg_actual_change 컬럼이 없어 레거시 포맷으로 저장했습니다."
                        )
                    except Exception as legacy_e:
                        if "Could not find the" in str(legacy_e):
                            logger.warning(
                                "sentiment_performance_daily 스키마가 더 오래되어 집계 저장을 건너뜁니다: %s",
                                legacy_e,
                            )
                            return
                        raise
                logger.info("감성 검증 일일 집계 재생성 완료: %s (%d행)", target_date, len(insert_rows))

        except Exception:
            logger.exception("감성 검증 일일 집계 재생성 실패: %s", target_date)
