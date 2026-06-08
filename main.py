import logging
import sys
import uuid

from pydantic import ValidationError
from src import ui

logging.basicConfig(
    format="%(asctime)s — %(name)s — %(levelname)s — %(message)s",
    level=logging.WARNING,
)

logger = logging.getLogger(__name__)

def run() -> int:
    ui.print_banner()

    try:
        from langchain_core.runnables import RunnableConfig
        from langgraph.types import Command

        from src.graph import build_email_agent
    except ValidationError as e:
        ui.show_config_error(
            "Pydantic Settings odrzucił konfigurację:\n"
            + "\n".join(f"  - {err['loc'][0]}: {err['msg']}" for err in e.errors())
        )
        return 2

    try:
        inputs = ui.collect_inputs()
    except (KeyboardInterrupt, EOFError):
        ui.show_cancelled()
        return 0

    graph = build_email_agent()
    thread_id = str(uuid.uuid4())
    config: RunnableConfig = {"configurable": {"thread_id": thread_id}}

    # Pierwszy invoke dostaje dict z inputami — startuje od węzła draft_email
    graph_input: dict[str, str] | Command = inputs

    try:
        while True:
            with ui.show_thinking("Agent pracuje ..."):
                graph.invoke(graph_input, config)

            snapshot = graph.get_state(config)

            # snapshot.next jest pustym tuple gdy graf doszedł do END.
            # Niepusty tuple oznacza że graf czeka — w naszej architekturze
            # to ZAWSZE oznacza interrupt() w human_review (jedyny węzeł
            # który wstrzymuje wykonanie).
            if not snapshot.next:
                file_path: str = snapshot.values.get("sent_path", "(brak ścieżki)")
                ui.show_sent(file_path)
                return 0

            draft: str = snapshot.values.get("draft", "")
            revision_count: int = snapshot.values.get("revision_count", 0)
            ui.show_draft(draft, revision_count)

            action, feedback = ui.ask_decision()

            graph_input = Command(resume={"action": action, "feedback": feedback})

    except (KeyboardInterrupt, EOFError):
        ui.show_cancelled()
        return 0
    except Exception as e:
        logger.exception("Niespodziewany błąd w pętli agenta")
        ui.show_error(f"{type(e).__name__}: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(run())
