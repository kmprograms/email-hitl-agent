# Human-in-the-Loop Email Agent

**Język / Language:** **Polski** | [English](README.en.md)

---

Demo agenta LangGraph piszącego maile B2B z obowiązkową akceptacją człowieka przed wysyłką. Pokazuje praktyczne użycie mechanizmu `interrupt()` z LangGraph — agent zatrzymuje się w połowie wykonania, czeka na decyzję użytkownika (zatwierdź / popraw z feedbackiem) i wznawia pracę dokładnie w tym samym miejscu.

CLI w terminalu, kolorowy interfejs przez `rich`, OpenAI jako backend LLM.

---

## Spis treści

- [Funkcjonalność](#funkcjonalność)
- [Architektura](#architektura)
- [Wymagania](#wymagania)
- [Instalacja](#instalacja)
- [Konfiguracja](#konfiguracja)
- [Uruchomienie](#uruchomienie)
- [Przykładowa sesja](#przykładowa-sesja)
- [Struktura projektu](#struktura-projektu)
- [Konfiguracja zaawansowana](#konfiguracja-zaawansowana)
- [Co dalej (produkcja)](#co-dalej-produkcja)

---

## Funkcjonalność

- Generowanie profesjonalnych maili po polsku na podstawie 3 inputów: odbiorca, firma, cel maila.
- **Human-in-the-loop**: po wygenerowaniu szkicu agent czeka na decyzję — `Y` (wyślij) lub `N` (popraw z feedbackiem).
- Pętla rewizji: model dostaje feedback i nanosi poprawki zamiast pisać od zera. Limit rewizji chroni przed nieskończoną pętlą (domyślnie 3, potem auto-approve).
- "Wysyłka" maila = zapis do pliku `.eml` w katalogu `sent/` (łatwa podmiana na SMTP / SendGrid bez ruszania reszty grafu).
- Czytelny terminalowy UI: banner, panele, spinner podczas wywołań LLM, kolorowe komunikaty błędów.

---

## Architektura

Graf LangGraph z trzema węzłami i mechanizmem `interrupt()` zatrzymującym wykonanie:

```
START → draft_email → human_review → send_email → END
              ↑              │
              └──────────────┘
              Command(goto="draft_email") przy revise
```

### Węzły

| Węzeł          | Rola                                                                                                    |
| -------------- | ------------------------------------------------------------------------------------------------------- |
| `draft_email`  | Wywołuje LLM (ChatOpenAI). Przy rewizji dokleja sekcję z feedbackiem od człowieka.                       |
| `human_review` | Wywołuje `interrupt()` — graf się zatrzymuje, stan trafia do checkpointera, wykonanie wraca do `main.py`.|
| `send_email`   | Zapisuje finalny mail do `sent/<timestamp>_<slug>.eml`.                                                  |

### Stan grafu (`EmailAgentState`)

`TypedDict` przekazywany między węzłami i serializowany przez checkpointer po każdym kroku. Trzyma input użytkownika, aktualny draft, decyzję człowieka, feedback, licznik rewizji i status.

### Checkpointer

`InMemorySaver` — stan w pamięci procesu. Po wyjściu z programu stan przepada. W produkcji wystarczy podmienić na `PostgresSaver` / `RedisSaver` żeby stan przeżył restart i pozwolił wznowić graf z innego procesu.

### Mechanizm `interrupt()`

`human_review` wywołuje `interrupt(payload)`:

1. LangGraph zapisuje aktualny stan do checkpointera.
2. Rzuca `GraphInterrupt` — `graph.invoke()` w `main.py` wraca normalnie.
3. Pętla w `main.py` czyta stan, pokazuje draft, pyta usera o decyzję.
4. Wznowienie: `graph.invoke(Command(resume={...}), config)` — payload z `Command.resume` ląduje jako wartość zwracana przez `interrupt()`, graf wraca w to samo miejsce.

Bez `interrupt()` musielibyśmy ręcznie zarządzać tym, gdzie agent się zatrzymał i co już zrobił.

---

## Wymagania

- **Python 3.13+** (wersja zapięta w `.python-version`).
- **[uv](https://docs.astral.sh/uv/)** — menedżer pakietów i wirtualnych środowisk (rekomendowany).
- **Klucz API OpenAI** — [https://platform.openai.com/api-keys](https://platform.openai.com/api-keys).

---

## Instalacja

```bash
git clone <url-repo> email-agent
cd email-agent
uv sync
```

`uv sync` utworzy `.venv/` i zainstaluje wszystkie zależności z `uv.lock` (deterministyczne wersje).

---

## Konfiguracja

Utwórz plik `.env` w katalogu głównym projektu:

```env
OPENAI_API_KEY=sk-...
```

### Wszystkie zmienne środowiskowe

| Zmienna              | Wymagana | Domyślnie       | Opis                                                  |
| -------------------- | -------- | --------------- | ----------------------------------------------------- |
| `OPENAI_API_KEY`     | tak      | —               | Klucz API OpenAI.                                     |
| `OPENAI_MODEL_NAME`  | nie      | `gpt-4.1-mini`  | Nazwa modelu ChatOpenAI.                              |
| `MODEL_TEMPERATURE`  | nie      | `0.3`           | Temperatura modelu (0.0–2.0).                         |
| `MAX_REVISIONS`      | nie      | `3`             | Limit rewizji przed auto-approve.                     |
| `SENT_DIR`           | nie      | `sent`          | Katalog, do którego zapisywane są "wysłane" maile.    |

Konfiguracja jest walidowana przez `pydantic-settings` na starcie aplikacji — brak klucza API rzuca czytelny błąd zamiast cichego crasha w trakcie pierwszego wywołania LLM.

---

## Uruchomienie

```bash
uv run python main.py
```

CLI poprosi kolejno o:

1. Imię i nazwisko odbiorcy.
2. Firmę odbiorcy.
3. Cel maila (np. *"follow-up po wczorajszym spotkaniu o integracji API"*).

Następnie wyświetli wygenerowany draft i poprosi o decyzję:

- **`Y`** — wyślij (mail trafia do `sent/`).
- **`N`** — odrzuć i podaj feedback. Agent wygeneruje poprawioną wersję uwzględniając Twoje uwagi.

Wyjście: `Ctrl+C` lub `Ctrl+D` w dowolnym momencie.

---

## Przykładowa sesja

```
┌─ Human-in-the-Loop Email Agent ────────────────────────────────┐
│ Demo LangGraph interrupt() — agent czeka na Twoją zgodę        │
└────────────────────────────────────────────────────────────────┘

Wprowadź dane maila do wygenerowania:

Imię i nazwisko odbiorcy: Jan Kowalski
Firma odbiorcy: Acme Corp
Cel maila (np. follow-up po wczorajszym spotkaniu): podsumowanie wczorajszego callu o integracji API

⠋ Agent pracuje ...

──────────────────── Wygenerowany szkic ────────────────────

┌────────────────────────────────────────────────────────────┐
│  Temat: Podsumowanie wczorajszego callu — integracja API   │
│                                                            │
│  Dzień dobry Panie Janie,                                  │
│                                                            │
│  Dziękuję za wczorajszą rozmowę. Poniżej krótkie           │
│  podsumowanie ustaleń...                                   │
│                                                            │
│  Pozdrawiam                                                │
└────────────────────────────────────────────────────────────┘

Co robimy?
  Y — wyślij maila tak jak jest
  N — odrzuć i podaj feedback do poprawy

Decyzja [Y/N]: N
Feedback dla agenta: Dodaj konkretną propozycję terminu kolejnego spotkania.

⠋ Agent pracuje ...

──────────────── Wersja po rewizji #1 ───────────────────────
...
```

---

## Struktura projektu

```
email-agent/
├── main.py              # Entry point — pętla CLI sterująca grafem
├── src/
│   ├── config.py        # Settings (pydantic-settings) — wczytuje .env
│   ├── model.py         # Factory ChatOpenAI
│   ├── state.py         # EmailAgentState (TypedDict) — stan grafu
│   ├── prompts.py       # Prompty systemowe i user (PL)
│   ├── nodes.py         # 3 węzły grafu: draft_email, human_review, send_email
│   ├── graph.py         # Montaż grafu + checkpointer
│   └── ui.py            # Warstwa CLI (rich) — banner, prompts, panele
├── sent/                # "Wysłane" maile (.eml) — gitignored
├── pyproject.toml       # Zależności + konfiguracja mypy
├── uv.lock              # Lockfile uv
├── .python-version      # 3.13
└── .env                 # Sekrety — gitignored, trzeba utworzyć
```

### Separation of concerns

- **`main.py`** zna tylko publiczne API: `build_email_agent()`, `graph.invoke()`, `Command`. Nie wie nic o promptach ani LLM.
- **`src/nodes.py`** zna LLM, prompty, IO plików — całą logikę domenową.
- **`src/ui.py`** zna tylko `rich` i input użytkownika. Można podmienić na FastAPI/Streamlit bez ruszania reszty.
- **`src/config.py`** — jedno źródło prawdy dla konfiguracji, walidowane na starcie.

---

## Konfiguracja zaawansowana

### Zmiana modelu

W `.env`:

```env
OPENAI_MODEL_NAME=gpt-5
MODEL_TEMPERATURE=0.7
```

### Wyższy limit rewizji

```env
MAX_REVISIONS=5
```

### Inny katalog na wysłane maile

```env
SENT_DIR=outbox
```

### Type-check

```bash
uv run mypy .
```

`mypy` jest skonfigurowany w `pyproject.toml` ze ścisłymi regułami (`disallow_untyped_defs`, `warn_return_any`).

---

## Co dalej (produkcja)

Projekt jest demem, ale architektura jest produkcyjna. Migracja do produkcji wymaga zmiany trzech rzeczy:

1. **Checkpointer**: `InMemorySaver` → `PostgresSaver` / `RedisSaver`. Stan przeżyje restart, można wznowić graf z innego procesu (np. webhook po godzinach).
2. **Warstwa wysyłki**: w `send_email` zamiast `Path.write_text()` wywołanie SMTP / SendGrid / Mailgun. Reszta grafu bez zmian.
3. **Warstwa UI**: CLI → FastAPI/WebSocket. Węzły są synchroniczne, więc w FastAPI trafiają do `ThreadPoolExecutor`, żeby nie blokować event loopa. `human_review` zamiast pytać w terminalu, czeka na żądanie HTTP z decyzją usera (UUID grafu = `thread_id`).

Nic z powyższych nie wymaga zmian w `state.py`, `prompts.py` ani `graph.py`.
