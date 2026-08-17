from langgraph.graph import END, START, StateGraph

from app.workflow.nodes import (
    compute_node,
    next_method_node,
    plan_node,
    report_node,
    retrieve_node,
    route_next_method,
    understand_node,
    verify_node,
)
from app.workflow.state import EvalState


def build_workflow():
    graph = StateGraph(EvalState)
    graph.add_node("understand", understand_node)
    graph.add_node("plan", plan_node)
    graph.add_node("next_method", next_method_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("compute", compute_node)
    graph.add_node("verify", verify_node)
    graph.add_node("report", report_node)

    graph.add_edge(START, "understand")
    graph.add_edge("understand", "plan")
    graph.add_edge("plan", "next_method")
    graph.add_conditional_edges(
        "next_method",
        route_next_method,
        {"retrieve": "retrieve", "verify": "verify"},
    )
    graph.add_edge("retrieve", "compute")
    graph.add_edge("compute", "next_method")
    graph.add_edge("verify", "report")
    graph.add_edge("report", END)
    return graph.compile(checkpointer=None)


workflow_app = build_workflow()
