from typing import Annotated, TypedDict
import operator

from langgraph.graph.message import add_messages


class EvalState(TypedDict):
    question: str
    requirement: dict
    methods: list[str]
    params: dict
    current_method: str
    context: str
    trend_sources: list[str]
    computations: Annotated[list, operator.add]
    verification: str
    report: str
    report_json: str
    messages: Annotated[list, add_messages]
    loop_count: int
