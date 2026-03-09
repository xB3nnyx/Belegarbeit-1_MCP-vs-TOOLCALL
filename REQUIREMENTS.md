# Anforderungen für das Experiment

## Technische Umgebung
- **Sprache:** Python 3.11+
- **Frameworks:**
    - `langchain`, `langchain-anthropic` (Orchestrierung des Agenten)
    - `fastmcp` (MCP-Wrapper-Server)
    - `fastapi`, `uvicorn` (lokaler Mock-API-Service)
- **Infrastruktur:** Ein lokaler Prozess, der die Mock-API bereitstellt (`uvicorn api_service.main:app`).

## Messinstrumente
- **Logger:** Zentrales Logging-Modul (`log_utils/logger.py`), das Unix-Timestamps in **Nanosekunden** (`time.time_ns()`) erfasst. Ergebnisse werden als JSONL-Einträge pro Run gespeichert.
- **Evaluator:** Regelbasierter Evaluator (`benchmark/judge.py`), der die Modell-Antwort gegen bekannte Ground-Truth-Fakten prüft und einen Score (0.0–1.0) vergibt.
- **Datenbank:** CSV-Dateien unter `LOGS/summaries/` (aggregierte Mittelwerte) und JSONL-Rohdaten unter `LOGS/raw/`.

## API-Keys
- Anthropic API Key (für Claude-Sonnet-4 als Proband).

## Tool-Calling
- Referenz: "https://github.com/oliverguhr/grundlagen-ki/blob/main/2_0_tool_calls.ipynb"