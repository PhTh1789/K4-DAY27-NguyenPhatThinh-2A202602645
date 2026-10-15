"""Time-travel helpers for inspecting and resuming durable graph checkpoints."""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command

from common.db import db_path
from exercises.exercise_4_audit import build_graph


async def checkpoint_history(thread_id: str, limit: int = 25) -> list[Any]:
    """Return recent checkpoints for a review thread, newest first."""
    async with AsyncSqliteSaver.from_conn_string(db_path()) as checkpointer:
        await checkpointer.setup()
        graph = build_graph(checkpointer)
        config = {"configurable": {"thread_id": thread_id}}
        return [snapshot async for snapshot in graph.aget_state_history(config, limit=limit)]


async def resume_from_checkpoint(
    thread_id: str,
    checkpoint_id: str,
    answer: dict[str, Any],
) -> dict[str, Any]:
    """Resume a historical checkpoint with a different reviewer answer."""
    async with AsyncSqliteSaver.from_conn_string(db_path()) as checkpointer:
        await checkpointer.setup()
        graph = build_graph(checkpointer)
        config = {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_id": checkpoint_id,
            }
        }
        return await graph.ainvoke(Command(resume=answer), config)
