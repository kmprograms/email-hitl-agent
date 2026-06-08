from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.nodes import draft_email, human_review, send_email
from src.state import EmailAgentState

"""
Montaż grafu agenta.

START → draft_email → human_review → send_email → END
              ↑              │
              └──────────────┘  Command(goto="draft_email") przy revise

human_review zwraca Command(goto=...) — routing zamknięty wewnątrz węzła.
Nie trzeba add_conditional_edges, kod jest prostszy do zrozumienia.

CHECKPOINTER:
InMemorySaver — stan grafu trzymany w pamięci procesu. Po wyjściu z programu
stan przepada.

W produkcyjnym API dbamy o persistence — stan przeżywa restart aplikacji, 
można wznowić graf z innego procesu, można obsłużyć tysiące jednoczesnych 
konwersacji.
"""

def build_email_agent() -> CompiledStateGraph:
    builder: StateGraph = StateGraph(EmailAgentState)

    builder.add_node("draft_email", draft_email)
    builder.add_node("human_review", human_review)
    builder.add_node("send_email", send_email)

    builder.add_edge(START, "draft_email")
    builder.add_edge("draft_email", "human_review")
    builder.add_edge("send_email", END)

    return builder.compile(checkpointer=InMemorySaver())