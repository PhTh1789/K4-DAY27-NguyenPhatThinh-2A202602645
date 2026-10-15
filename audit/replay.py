"""Replay a review session from the audit trail.

Usage:
    uv run python -m audit.replay --thread <thread_id>
    uv run python -m audit.replay --list                # list recent threads

The script reads `audit_events` (human-readable timeline). The LangGraph
SqliteSaver checkpoint tables live in the same .db file but are queried
separately by the LangGraph runtime, not by this tool.
"""

from __future__ import annotations

import argparse
import asyncio
import json

from rich.console import Console
from rich.table import Table

from common.db import db_conn, replay_events
from audit.time_travel import checkpoint_history, resume_from_checkpoint


RISK_COLOR = {"low": "green", "med": "yellow", "high": "red"}


async def list_threads() -> None:
    console = Console()
    async with db_conn() as conn:
        async with conn.execute(
            """
            SELECT thread_id,
                   pr_url,
                   MIN(timestamp)        AS started,
                   MAX(timestamp)        AS last_event,
                   MAX(risk_level)       AS worst_risk,
                   COUNT(*)              AS events
              FROM audit_events
             GROUP BY thread_id, pr_url
             ORDER BY MAX(timestamp) DESC
             LIMIT 25
            """
        ) as cur:
            rows = await cur.fetchall()

    table = Table(title="Recent review sessions")
    for col in ("thread_id", "pr_url", "started", "last_event", "worst_risk", "events"):
        table.add_column(col)
    for r in rows:
        table.add_row(
            r["thread_id"],
            r["pr_url"],
            str(r["started"]),
            str(r["last_event"]),
            str(r["worst_risk"]),
            str(r["events"]),
        )
    console.print(table)


async def replay(thread_id: str) -> None:
    console = Console()
    events = await replay_events(thread_id)

    if not events:
        console.print(f"[red]No events found for thread {thread_id}[/red]")
        return

    console.rule(f"[bold]Replay {thread_id}")
    for ev in events:
        risk = ev["risk_level"]
        risk_colored = f"[{RISK_COLOR.get(risk, 'white')}]{risk:<4}[/]"
        reviewer = ev["reviewer_id"] or "-"
        reason = (ev["reason"] or "")[:60]
        console.print(
            f"[dim]{ev['timestamp']}[/dim]  "
            f"[cyan]{ev['action']:<18}[/cyan] "
            f"conf=[bold]{ev['confidence']:.2f}[/bold] "
            f"risk={risk_colored} "
            f"decision=[magenta]{ev['decision']:<10}[/magenta] "
            f"reviewer={reviewer:<14} "
            f"{ev['execution_time_ms']:>5}ms  "
            f"[dim]{reason}[/dim]"
        )


async def calibration() -> None:
    """Report confidence for human decisions and their approval rate."""
    console = Console()
    async with db_conn() as conn:
        async with conn.execute(
            """
            SELECT COUNT(*) AS decisions,
                   SUM(CASE WHEN decision = 'approve' THEN 1 ELSE 0 END) AS approvals,
                   AVG(confidence) AS average_confidence
              FROM audit_events
             WHERE action = 'commit'
               AND decision IN ('approve', 'reject')
            """
        ) as cur:
            row = await cur.fetchone()

    decisions = row["decisions"] or 0
    approvals = row["approvals"] or 0
    average_confidence = row["average_confidence"]
    if not decisions:
        console.print("[yellow]No human approval decisions found yet.[/yellow]")
        return
    approval_rate = approvals / decisions
    console.print("[bold]Confidence calibration (human decisions)[/bold]")
    console.print(f"Decisions:          {decisions}")
    console.print(f"Approved:           {approvals}")
    console.print(f"Approval rate:      {approval_rate:.1%}")
    console.print(f"Average confidence: {average_confidence:.1%}")


async def history(thread_id: str, limit: int) -> None:
    console = Console()
    snapshots = await checkpoint_history(thread_id, limit)
    if not snapshots:
        console.print(f"[red]No checkpoints found for thread {thread_id}[/red]")
        return
    table = Table(title=f"Checkpoints for {thread_id}")
    table.add_column("#")
    table.add_column("checkpoint_id")
    table.add_column("next")
    table.add_column("state keys")
    for index, snapshot in enumerate(snapshots):
        checkpoint_id = snapshot.config["configurable"].get("checkpoint_id", "?")
        table.add_row(str(index), checkpoint_id, str(snapshot.next), ", ".join(snapshot.values))
    console.print(table)


async def resume_checkpoint(thread_id: str, checkpoint_id: str, answer: str) -> None:
    result = await resume_from_checkpoint(thread_id, checkpoint_id, json.loads(answer))
    Console().print(result)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--thread", help="Replay one thread by id")
    parser.add_argument("--list", action="store_true", help="List recent threads")
    parser.add_argument("--calibration", action="store_true", help="Report confidence vs human approvals")
    parser.add_argument("--history", help="List durable checkpoints for a thread")
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--resume-checkpoint", help="Resume a historical checkpoint id")
    parser.add_argument("--answer", help="JSON reviewer answer for --resume-checkpoint")
    args = parser.parse_args()

    if args.history:
        asyncio.run(history(args.history, args.limit))
    elif args.resume_checkpoint and args.thread and args.answer:
        asyncio.run(resume_checkpoint(args.thread, args.resume_checkpoint, args.answer))
    elif args.calibration:
        asyncio.run(calibration())
    elif args.list:
        asyncio.run(list_threads())
    elif args.thread:
        asyncio.run(replay(args.thread))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
