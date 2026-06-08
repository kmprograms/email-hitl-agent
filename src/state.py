from typing import TypedDict

"""
Stan agenta przekazywany między węzłami grafu LangGraph.

Checkpointer (InMemorySaver) serializuje ten stan po każdym kroku i pozwala 
wznowić graf z dokładnie tego miejsca po interrupt().
"""

class EmailAgentState(TypedDict, total=False):
    # --- Input ---
    recipient_name: str
    recipient_company: str
    purpose: str

    # --- Draft ---
    draft: str

    # --- Human Review ---
    human_decision: str  # "approve" | "revise"
    human_feedback: str

    # --- Send ---
    sent_path: str

    # --- Meta ---
    revision_count: int
    status: str  # drafting | awaiting_review | sending | sent