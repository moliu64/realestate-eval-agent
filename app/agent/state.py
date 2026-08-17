from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    question: str
    context: str
    messages: Annotated[list, add_messages]
    answer: str
