import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import Command, interrupt

from src.config import settings
from src.model import create_model
from src.prompts import DRAFT_HUMAN_PROMPT, DRAFT_SYSTEM_PROMPT, REVISION_SECTION
from src.state import EmailAgentState

"""
Węzły grafu agenta.

Każdy węzeł:
1. Przyjmuje EmailAgentState
2. Wykonuje logikę
3. Zwraca dict z aktualizacjami stanu LUB Command(goto=...)

Węzły są SYNCHRONICZNE — graf wywołujemy z głównego wątku.
W produkcyjnym API te same węzły poszłyby do ThreadPoolExecutor żeby nie
blokować Event Loop FastAPI.
"""

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------
# NODE 1: DRAFT EMAIL
# -----------------------------------------------------------------------

def draft_email(state: EmailAgentState) -> dict:
    """
    Generuje szkic maila. Przy rewizji dokleja sekcję z feedbackiem
    od człowieka — model widzi co poprawić zamiast pisać od zera.
    """
    revision_count: int = state.get("revision_count", 0)
    is_revision: bool = revision_count > 0
    label = f"draft rewizja #{revision_count}" if is_revision else "draft"
    logger.info(f"[{label}] Generuję szkic ...")

    feedback_section: str = ""
    if is_revision:
        feedback_section = REVISION_SECTION.format(
            revision_count=revision_count,
            human_feedback=state.get("human_feedback", ""),
        )

    model = create_model(settings.model_temperature)
    response = model.invoke([
        SystemMessage(content=DRAFT_SYSTEM_PROMPT),
        HumanMessage(content=DRAFT_HUMAN_PROMPT.format(
            recipient_name=state.get("recipient_name", ""),
            recipient_company=state.get("recipient_company", ""),
            purpose=state.get("purpose", ""),
            feedback_section=feedback_section,
        )),
    ])

    draft: str = str(response.content).strip()
    logger.info(f"[{label}] Szkic gotowy: {len(draft)} znaków")

    return {
        "draft": draft,
        "status": "awaiting_review",
    }

# -----------------------------------------------------------------------
# NODE 2: HUMAN REVIEW
# -----------------------------------------------------------------------

def human_review(state: EmailAgentState) -> Command:
    """
    Zatrzymuje graf przez interrupt() i czeka na decyzję człowieka.

    interrupt() to mechanizm LangGrapha który:
    1. Zapisuje stan grafu do checkpointera (InMemorySaver).
    2. Wyrzuca specjalny wyjątek GraphInterrupt do wywołującego.
    3. Po stronie wywołującego graph.invoke() zwraca normalnie — graf
       jest "uśpiony" przed tym węzłem.
    4. Wznowienie: graph.invoke(Command(resume=...), config) wraca
       w to samo miejsce, payload `resume` ląduje jako return value
       z interrupt().

    Bez interrupt() musiałbyś sam zarządzać stanem — gdzie agent się
    zatrzymał, co już zrobił, co czeka. Z interrupt() LangGraph robi
    to za Ciebie. Możesz wznowić graf po godzinie, po restarcie aplikacji
    (wtedy persistence dla checkpointera), z innego procesu.

    Routing przez Command(goto=...) — sami decydujemy gdzie wraca graf
    w zależności od decyzji człowieka.
    """
    revision_count: int = state.get("revision_count", 0)
    logger.info(f"[human_review] Czekam na decyzję (rewizja #{revision_count})")

    decision: dict[str, str] = interrupt({
        "type": "review_email",
        "draft": state.get("draft", ""),
        "revision_count": revision_count,
        "message": "Zatwierdź mail (approve) lub odrzuć z feedbackiem (revise).",
    })

    action: str = decision.get("action", "approve")
    feedback: str = decision.get("feedback", "")

    logger.info(f"[human_review] Decyzja: {action}")

    # --- APPROVE: do send_email ---
    if action == "approve":
        return Command(
            update={
                "human_decision": "approve",
                "human_feedback": "",
                "status": "sending",
            },
            goto="send_email",
        )

    # --- REVISE: ochrona przed nieskończoną pętlą ---
    new_count = revision_count + 1
    if new_count >= settings.max_revisions:
        logger.warning(
            f"[human_review] Limit rewizji ({settings.max_revisions}) osiągnięty. Auto-approve."
        )
        return Command(
            update={
                "human_decision": "approve",
                "human_feedback": f"Auto-approved po {settings.max_revisions} rewizjach.",
                "status": "sending",
            },
            goto="send_email",
        )

    # --- REVISE: wracamy do draft_email z feedbackiem ---
    return Command(
        update={
            "human_decision": "revise",
            "human_feedback": feedback,
            "revision_count": new_count,
            "status": "drafting",
        },
        goto="draft_email",
    )

# -----------------------------------------------------------------------
# NODE 3: SEND EMAIL
# -----------------------------------------------------------------------

def send_email(state: EmailAgentState) -> dict:
    """
    'Wysyła' maila — u nas zapisuje go do pliku .eml w katalogu sent/.
    W produkcji tu byłby smtplib / SendGrid. Logika reszty grafu nie
    zmienia się.
    """
    draft: str = state.get("draft", "")
    if not draft:
        raise ValueError("Brak treści maila do wysłania.")

    company: str = state.get("recipient_company", "unknown")
    slug: str = re.sub(r"[^a-z0-9]+", "-", company.lower().strip())[:40].strip("-") or "unknown"
    # UTC w nazwie pliku — niezależne od strefy czasowej hosta
    timestamp: str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename: str = f"{timestamp}_{slug}.eml"

    sent_dir = Path(settings.sent_dir)
    sent_dir.mkdir(parents=True, exist_ok=True)
    file_path = sent_dir / filename

    file_path.write_text(draft, encoding="utf-8")

    logger.info(f"[send_email] Mail 'wysłany' (zapisany): {file_path}")

    return {
        "sent_path": str(file_path),
        "status": "sent",
    }