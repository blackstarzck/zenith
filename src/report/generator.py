"""
일일 분석 리포트 생성기.
매일 자정에 전일 매매 데이터를 분석하여 마크다운 리포트를 생성합니다.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from src.storage.client import StorageClient

logger = logging.getLogger(__name__)


def generate_daily_report(
    storage: StorageClient,
    report_date: date,
    total_balance: float,
    net_profit: float,
    initial_balance: float,
) -> str:
    """전일 매매 데이터를 분석하여 마크다운 리포트를 생성하고 DB에 저장합니다.

    Args:
        storage: Supabase 스토리지 클라이언트
        report_date: 리포트 대상 날짜
        total_balance: 당일 최종 자산
        net_profit: 당일 실현 손익
        initial_balance: 당일 시작 자산

    Returns:
        생성된 마크다운 리포트 문자열
    """
    # ── 1. 데이터 수집 ────────────────────────────────────
    trades = _get_trades_for_date(storage, report_date)
    logs = _get_logs_for_date(storage, report_date)

    # 매수/매도 분류
    buys = [t for t in trades if t.get("side") == "bid"]
    sells = [t for t in trades if t.get("side") == "ask"]

    # 승/패 집계
    winning = [t for t in sells if (t.get("pnl") or 0) > 0]
    losing = [t for t in sells if (t.get("pnl") or 0) < 0]
    breakeven = [t for t in sells if (t.get("pnl") or 0) == 0]

    total_pnl = sum(t.get("pnl", 0) or 0 for t in sells)
    win_count = len(winning)
    loss_count = len(losing)
    trade_count = len(trades)
    win_rate = (win_count / len(sells) * 100) if sells else 0
    daily_return_pct = (net_profit / initial_balance * 100) if initial_balance > 0 else 0

    # ── 2. 마크다운 리포트 생성 ──────────────────────────
    lines: list[str] = []

    # 헤더
    lines.append(f"# 📊 일일 트레이딩 리포트 — {report_date.isoformat()}")
    lines.append("")

    # 요약
    lines.append("## 📋 요약")
    lines.append("")
    lines.append(f"| 항목 | 값 |")
    lines.append(f"|---|---|")
    lines.append(f"| 시작 자산 | {initial_balance:,.0f} KRW |")
    lines.append(f"| 최종 자산 | {total_balance:,.0f} KRW |")
    lines.append(f"| 당일 손익 | {net_profit:+,.0f} KRW ({daily_return_pct:+.2f}%) |")
    lines.append(f"| 총 거래 | {trade_count}건 (매수 {len(buys)} / 매도 {len(sells)}) |")
    lines.append(f"| 승률 | {win_rate:.1f}% ({win_count}승 {loss_count}패 {len(breakeven)}무) |")
    lines.append(f"| 총 실현 손익 | {total_pnl:+,.0f} KRW |")
    lines.append("")

    # 매매 상세
    if trades:
        lines.append("## 📈 매매 상세")
        lines.append("")

        if buys:
            lines.append("### 매수")
            lines.append("")
            lines.append("| 시간 | 종목 | 가격 | 금액 | 사유 |")
            lines.append("|---|---|---|---|---|")
            for t in buys:
                time_str = _format_time(t.get("created_at", ""))
                reason = t.get("reason", "-") or "-"
                lines.append(
                    f"| {time_str} | {t['symbol']} | {t['price']:,.2f} | "
                    f"{t['amount']:,.0f} KRW | {reason} |"
                )
            lines.append("")

        if sells:
            lines.append("### 매도")
            lines.append("")
            lines.append("| 시간 | 종목 | 가격 | 금액 | 손익 | 사유 |")
            lines.append("|---|---|---|---|---|---|")
            for t in sells:
                time_str = _format_time(t.get("created_at", ""))
                pnl = t.get("pnl", 0) or 0
                pnl_emoji = "🟢" if pnl > 0 else ("🔴" if pnl < 0 else "⚪")
                reason = t.get("reason", "-") or "-"
                lines.append(
                    f"| {time_str} | {t['symbol']} | {t['price']:,.2f} | "
                    f"{t['amount']:,.0f} KRW | {pnl_emoji} {pnl:+,.0f} | {reason} |"
                )
            lines.append("")
    else:
        lines.append("## 📈 매매 상세")
        lines.append("")
        lines.append("당일 매매 내역이 없습니다.")
        lines.append("")

    # 손익 분석
    if sells:
        lines.append("## 🔍 손익 분석")
        lines.append("")

        if winning:
            best = max(winning, key=lambda t: t.get("pnl", 0) or 0)
            avg_win = sum(t.get("pnl", 0) or 0 for t in winning) / len(winning)
            lines.append(f"**최대 수익 거래**: {best['symbol']} — {best.get('pnl', 0):+,.0f} KRW")
            lines.append(f"  - 사유: {best.get('reason', '-') or '-'}")
            lines.append(f"  - 평균 수익: {avg_win:+,.0f} KRW")
            lines.append("")

        if losing:
            worst = min(losing, key=lambda t: t.get("pnl", 0) or 0)
            avg_loss = sum(t.get("pnl", 0) or 0 for t in losing) / len(losing)
            lines.append(f"**최대 손실 거래**: {worst['symbol']} — {worst.get('pnl', 0):+,.0f} KRW")
            lines.append(f"  - 사유: {worst.get('reason', '-') or '-'}")
            lines.append(f"  - 평균 손실: {avg_loss:+,.0f} KRW")
            lines.append("")

        # 종목별 손익 요약
        symbol_pnl: dict[str, float] = {}
        for t in sells:
            sym = t["symbol"]
            symbol_pnl[sym] = symbol_pnl.get(sym, 0) + (t.get("pnl", 0) or 0)

        if symbol_pnl:
            lines.append("### 종목별 손익")
            lines.append("")
            lines.append("| 종목 | 합산 손익 |")
            lines.append("|---|---|")
            for sym, pnl in sorted(symbol_pnl.items(), key=lambda x: x[1], reverse=True):
                emoji = "🟢" if pnl > 0 else ("🔴" if pnl < 0 else "⚪")
                lines.append(f"| {sym} | {emoji} {pnl:+,.0f} KRW |")
            lines.append("")

    # 시스템 이벤트 요약
    warning_logs = [l for l in logs if l.get("level") in ("WARNING", "ERROR", "CRITICAL")]
    if warning_logs:
        lines.append("## ⚠️ 시스템 이벤트")
        lines.append("")
        lines.append(f"경고/오류 {len(warning_logs)}건 발생:")
        lines.append("")
        for log in warning_logs[:20]:  # 최대 20건
            time_str = _format_time(log.get("created_at", ""))
            lines.append(f"- `{log['level']}` {time_str} — {log['message']}")
        if len(warning_logs) > 20:
            lines.append(f"- ... 외 {len(warning_logs) - 20}건")
        lines.append("")

    # 푸터
    lines.append("---")
    lines.append(f"*Zenith Trading Bot — 자동 생성 리포트*")

    content = "\n".join(lines)

    # ── 3. DB 저장 ────────────────────────────────────────
    storage.upsert_daily_report(
        report_date=report_date,
        content=content,
        total_balance=total_balance,
        net_profit=net_profit,
        trade_count=trade_count,
        win_count=win_count,
        loss_count=loss_count,
    )

    logger.info("일일 리포트 생성 완료: %s (%d거래, %d승 %d패)", report_date, trade_count, win_count, loss_count)
    return content


# ── 유틸리티 ─────────────────────────────────────────────


def _get_trades_for_date(
    storage: StorageClient,
    target_date: date,
) -> list[dict[str, Any]]:
    """특정 날짜의 매매 내역을 조회합니다."""
    trades = storage.get_trades(limit=500)
    date_str = target_date.isoformat()
    return [
        t for t in trades
        if t.get("created_at", "").startswith(date_str)
    ]


def _get_logs_for_date(
    storage: StorageClient,
    target_date: date,
) -> list[dict[str, Any]]:
    """특정 날짜의 시스템 로그를 조회합니다."""
    try:
        start = f"{target_date.isoformat()}T00:00:00"
        end = f"{target_date.isoformat()}T23:59:59"
        result = (
            storage._client.table("system_logs")
            .select("*")
            .gte("created_at", start)
            .lte("created_at", end)
            .order("created_at", desc=False)
            .limit(500)
            .execute()
        )
        return result.data or []
    except Exception:
        logger.exception("리포트용 로그 조회 실패")
        return []


def _format_time(iso_str: str) -> str:
    """ISO 타임스탬프에서 HH:MM:SS 부분만 추출합니다."""
    if not iso_str:
        return "-"
    try:
        # "2025-01-15T09:30:45.123456" → "09:30:45"
        time_part = iso_str.split("T")[1] if "T" in iso_str else iso_str
        return time_part[:8]
    except (IndexError, TypeError):
        return "-"
