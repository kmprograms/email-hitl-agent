from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.rule import Rule
from rich.status import Status

# JEDNA instancja Console na cały proces aplikacji.
# Console wewnętrznie trzyma bufor renderowania, detekcję kolorów terminala, szerokości
# linii itd. Tworzenie nowej instancji za każdym razem byłoby niewydajne.
console = Console()

def print_banner() -> None:
    """Wyświetla powitalny banner aplikacji na starcie."""

    # Pusta linia odstępu
    console.print()

    # Panel.fit — szerokość ramki dopasowana do najdłuższej linii treści, NIE
    # rozciąga się na cały terminal.
    console.print(Panel.fit(
        # [bold cyan] ... [/bold cyan] — Rich markup. Wycinek tekstu pomiędzy
        # tagami zostanie wyrenderowany z tym stylem. \n to twardy newline.
        "[bold cyan]Human-in-the-Loop Email Agent[/bold cyan]\n"
        "[dim]Demo LangGraph interrupt() — agent czeka na Twoją zgodę zanim cokolwiek zrobi[/dim]",
        # Kolor obramowania panelu (sama ramka, nie treść).
        border_style="cyan",
    ))

    # Druga pusta linia — oddzielenie banneru od następnej sekcji.
    console.print()


def collect_inputs() -> dict[str, str]:
    """
    Zbiera od użytkownika dane potrzebne do wygenerowania maila.
    Zwraca dict z 3 polami pasującymi 1:1 do EmailAgentState (Input section).
    Dzięki temu w main.py możemy bezpośrednio przekazać ten dict do graph.invoke().
    """
    console.print("[bold]Wprowadź dane maila do wygenerowania:[/bold]\n")

    recipient_name = _ask_nonempty("Imię i nazwisko odbiorcy")
    recipient_company = _ask_nonempty("Firma odbiorcy")
    purpose = _ask_nonempty("Cel maila (np. follow-up po wczorajszym spotkaniu)")

    # Klucze celowo zgodne z polami w EmailAgentState.
    return {
        "recipient_name": recipient_name,
        "recipient_company": recipient_company,
        "purpose": purpose,
    }


def show_draft(draft: str, revision_count: int) -> None:
    """
    Renderuje wygenerowany szkic maila w żółtej ramce.
    Tytuł zmienia się w zależności od tego czy to pierwsza wersja czy rewizja.
    """

    title = (
        f"Wersja po rewizji #{revision_count}"
        if revision_count > 0
        else "Wygenerowany szkic"
    )

    console.print()
    # Rule — pozioma linia z tytułem pośrodku. Wizualnie sygnalizuje nową sekcję.
    console.print(Rule(f"[bold yellow]{title}[/bold yellow]"))
    console.print()

    console.print(Panel(
        # Sam tekst draftu — bez Rich markup, bo treść maila to surowy tekst
        # od LLM i nie chcemy żeby przypadkowe [foo] w treści zostało
        # zinterpretowane jako tag.
        draft,
        # Żółty — kolor "do uwagi", coś co user musi przeczytać.
        border_style="yellow",
        # padding=(góra/dół, lewo/prawo) — wnętrze panelu z odstępem,
        # tekst nie klei się do ramki. (1, 2) = 1 linia góra/dół, 2 spacje boki.
        padding=(1, 2),
    ))
    console.print()


def ask_decision() -> tuple[str, str]:
    """
    Pyta usera o decyzję: zatwierdzić mail (approve) czy odrzucić z feedbackiem (revise).
    """

    # Wyświetlamy opcje wyboru.
    console.print("[bold]Co robimy?[/bold]")
    console.print("  [bold green]Y[/bold green] — wyślij maila tak jak jest")
    console.print("  [bold red]N[/bold red] — odrzuć i podaj feedback do poprawy")
    console.print()

    while True:
        answer = Prompt.ask(
            "[bold]Decyzja[/bold] \\[Y/N]",
            # choices — Rich będzie pytał ponownie aż user wpisze jedną z dozwolonych
            # wartości.
            choices=["Y", "N", "y", "n"],
            # Nie pokazuj listy choices na końcu prompta
            show_choices=False,
        ).strip().upper()

        # Approve — wracamy natychmiast bez pytania o feedback (nie ma sensu).
        if answer == "Y":
            return "approve", ""

        # Revise — pytamy o feedback w osobnym prompcie. User może wpisać dowolny tekst.
        feedback = Prompt.ask("[red]Feedback dla agenta[/red]").strip()

        # Walidacja: pusty feedback nie ma sensu — model nie wie co poprawić.
        if not feedback:
            console.print("[red]Feedback nie może być pusty. Spróbuj ponownie.[/red]\n")
            continue

        return "revise", feedback


def show_sent(file_path: str) -> None:
    """Zielony panel sukcesu po zakończeniu cyklu — agent skończył pracę."""
    console.print()
    console.print(Panel(
        f"[bold green]Mail wysłany[/bold green] [dim](u nas: zapisany do pliku)[/dim]\n"
        f"[dim]{file_path}[/dim]",
        border_style="green",
        padding=(1, 2),
    ))
    console.print()


def show_error(message: str) -> None:
    """Czerwony panel błędu — coś poszło nie tak w runtime grafu."""
    console.print()
    console.print(Panel(
        f"[bold red]Błąd[/bold red]\n{message}",
        border_style="red",
        padding=(1, 2),
    ))
    console.print()


def show_cancelled() -> None:
    """Krótki komunikat gdy user anulował (Ctrl+C / EOF)."""
    console.print()
    console.print("[yellow]Anulowane przez użytkownika.[/yellow]")
    console.print()


def show_thinking(message: str = "Agent pracuje ...") -> Status:
    """
    Context manager — pokazuje spinner przy długich operacjach LLM.
    Spinner Rich uruchamia animację w OSOBNYM wątku (renderer), ale nie
    udostępniamy mu żadnego współdzielonego stanu — to czysto kosmetyczne.
    Nasz kod cały czas działa w głównym wątku.
    """
    return console.status(f"[cyan]{message}[/cyan]", spinner="dots")


def show_config_error(detail: str) -> None:
    """
    Czytelny komunikat gdy brakuje .env / klucza API.
    """
    console.print()
    console.print(Panel(
        "[bold red]Brak konfiguracji[/bold red]\n\n"
        f"{detail}\n\n"
        "[bold]Co zrobić:[/bold]\n"
        "  1. [cyan]cp .env.example .env[/cyan]\n"
        "  2. Otwórz [cyan].env[/cyan] i wstaw swój [cyan]OPENAI_API_KEY[/cyan]\n"
        "  3. Uruchom ponownie: [cyan]uv run python main.py[/cyan]",
        border_style="red",
        padding=(1, 2),
    ))
    console.print()

def _ask_nonempty(label: str, max_length: int = 500) -> str:
    """
    Pyta o niepuste wejście. Limit długości chroni przed wklejeniem
    50 KB tekstu jako 'cel maila'.
    """

    while True:
        # Prompt.ask zwraca string. .strip() usuwa leading/trailing whitespace —
        # user może przypadkiem wkleić tekst z odstępem albo nacisnąć spację.
        value = Prompt.ask(f"[cyan]{label}[/cyan]").strip()

        # Walidacja 1: puste dane
        # continue → wracamy na początek while, pytamy ponownie.
        if not value:
            console.print("[red]Pole nie może być puste.[/red]\n")
            continue

        # Walidacja 2: długość.
        # len(str) zwraca liczbę znaków Unicode (nie bajtów) — to co user widzi.
        if len(value) > max_length:
            console.print(
                f"[red]Pole jest za długie ({len(value)} znaków, limit {max_length}).[/red]\n"
            )
            continue

        # Obie walidacje przeszły — zwracamy wartość, pętla się kończy.
        return value