"""Minimal Send-based multi-reviewer escalation graph.

The caller supplies each reviewer's answers, which keeps this bonus deterministic
and avoids posting duplicate GitHub comments during a demo.
"""

from __future__ import annotations

import argparse
import json
from operator import add
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send


class FanoutState(TypedDict, total=False):
    questions: list[str]
    reviewer_answers: dict[str, dict[str, str]]
    reviewer_id: str
    answers: Annotated[list[dict[str, dict[str, str]]], add]


def fan_out_reviewers(state: FanoutState) -> list[Send]:
    """Send the same escalation questions to two independent reviewers."""
    reviewers = tuple(state.get("reviewer_answers", {}))
    if not reviewers:
        reviewers = ("reviewer-1", "reviewer-2")
    return [
        Send(
            "reviewer",
            {
                "questions": state["questions"],
                "reviewer_id": reviewer_id,
                "reviewer_answers": state.get("reviewer_answers", {}),
            },
        )
        for reviewer_id in reviewers
    ]


def collect_reviewer_answers(state: FanoutState) -> dict:
    reviewer_id = state["reviewer_id"]
    answers = state.get("reviewer_answers", {}).get(reviewer_id, {})
    return {"answers": [{reviewer_id: answers}]}


def start_fanout() -> dict:
    return {}


def build_fanout_graph():
    graph = StateGraph(FanoutState)
    graph.add_node("reviewers", start_fanout)
    graph.add_node("reviewer", collect_reviewer_answers)
    graph.add_edge(START, "reviewers")
    graph.add_conditional_edges("reviewers", fan_out_reviewers, ["reviewer"])
    graph.add_edge("reviewer", END)
    return graph.compile()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--questions", nargs="+", required=True)
    parser.add_argument(
        "--answers",
        required=True,
        help='JSON mapping reviewer ids to answer mappings',
    )
    args = parser.parse_args()
    answers = json.loads(args.answers)
    result = build_fanout_graph().invoke(
        {"questions": args.questions, "reviewer_answers": answers}
    )
    print(json.dumps(result["answers"], indent=2))


if __name__ == "__main__":
    main()
