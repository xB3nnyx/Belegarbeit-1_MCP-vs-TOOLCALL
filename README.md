# MCP vs. Direct Tool-Calling - Belegarbeit (Claude-Sonnet-4 Edition)

Ein experimenteller Benchmark, der den **Model Context Protocol (MCP)**-Ansatz mit dem **Direct Tool-Calling**-Ansatz (LangChain native) vergleicht. Gemessen werden Latenz, Protokoll-Overhead und Robustheit bei sauberen und unsauberen APIs.

---

## Experiment-Überblick

Ein Claude-Sonnet-4-Agent bekommt eine natürlichsprachliche Aufgabe und muss dabei HTTP-Endpunkte einer lokalen Mock-API aufrufen. Der Benchmark führt dasselbe Szenario 100-mal durch und loggt jeden Schritt mit Nanosekunden-Präzision.

| Ansatz | Beschreibung |
|---|---|
| **Direct (Tool-Calling)** | Claude-Sonnet-4 nutzt die native Anthropic Tool-Use API, um Python-Funktionen direkt auszuführen. LangChain übernimmt die Orchestrierung; der HTTP-Call an die Mock-API erfolgt ohne Protokoll-Zwischenschicht. |
| **MCP** | Gleicher LLM-Mechanismus (Tool-Use), aber die Tool-Ausführung wird über einen FastMCP-Server geleitet (JSON-RPC über stdio). Die zusätzliche Transportschicht ist der zentrale Untersuchungsgegenstand. |

### Phasen

| Phase | API-Zustand | Endpunkte |
|---|---|---|
| `sunny` | Sauber, konsistente Schemata | 1 (Inventory + Stock) |
| `dirty` | Inkonsistente Schemata, sporadische 500-Fehler | 1 |
| `multi_sunny` | Sauber | 5 (+ Orders, Customers, Discounts) |
| `multi_dirty` | Schmutzig | 5 |

---

## Projektstruktur

```
.
├── api_service/
│   └── main.py              # FastAPI Mock-API (sunny + dirty Endpunkte)
├── approaches/
│   ├── direct_calling.py    # LangChain Tools für direkten API-Aufruf
│   └── mcp_wrapper.py       # FastMCP Server-Wrapper mit Response-Normalisation
├── benchmark/
│   ├── runner.py            # Orchestrierung der Benchmark-Iterationen
│   └── judge.py             # Deterministischer Evaluator: bewertet LLM-Antworten post-run
├── log_utils/
│   └── logger.py            # RunLogger: schreibt ein strukturiertes JSONL-Record pro Run
├── LOGS/
│   ├── raw/                 # JSONL-Rohdaten (ein Record pro Run)
│   └── summaries/           # Aggregierte CSV-Auswertungen
├── REQUIREMENTS.md
├── EXPERIMENT_PROTOCOL.md
├── LOGGING_CONCEPT.md
└── requirements.txt
```

---

## Setup

```bash
# 1. Virtuelle Umgebung erstellen und aktivieren
python -m venv venv
venv\Scripts\activate       # Windows

# 2. Abhängigkeiten installieren
pip install -r requirements.txt

# 3. API-Key setzen (.env Datei im Root anlegen)
cp .env.example .env
# → ANTHROPIC_API_KEY=sk-ant-api03-... eintragen
```

---

## Benchmark ausführen

**Schritt 1 — Mock-API starten** (in einem separaten Terminal, laufen lassen):

```bash
uvicorn api_service.main:app --host 127.0.0.1 --port 8000
```

Die API ist erreichbar unter `http://localhost:8000`. OpenAPI-Docs: `http://localhost:8000/docs`

**Schritt 2 — Benchmark konfigurieren** in `benchmark/runner.py`:

```python
CONFIG = {
    "case":       "sunny",                      # "sunny" | "dirty" | "multi_sunny" | "multi_dirty"
    "modus":      "direct",                     # "direct" | "mcp"
    "iterations": 100,                          # Anzahl Durchläufe
    "model":      "claude-sonnet-4-20250514",
}
```

**Schritt 3 — Benchmark starten**:

```bash
python -m benchmark.runner
```

> **Hinweis (Windows, venv nicht aktiviert):** `.\venv\Scripts\python.exe -m benchmark.runner`

Die Ergebnisse landen in `LOGS/raw/<scenario>_<approach>.jsonl`
 und werden danach zu `LOGS/summaries/` aggregiert. Die Qualitätsbewertung (`judge_score`) wird automatisch am Ende jedes Laufs berechnet.

---

## Das vollständige Experiment durchführen

Das Experiment besteht aus **8 Läufen** (4 Szenarien × 2 Ansätze = 800 Iterationen gesamt).
Die API muss während aller Läufe laufen.

### Reihenfolge der Läufe

| Lauf | `case` | `modus` | Ausgabedatei |
|---|---|---|---|
| 1 | `sunny` | `direct` | `LOGS/raw/sunny_direct.jsonl` |
| 2 | `sunny` | `mcp` | `LOGS/raw/sunny_mcp.jsonl` |
| 3 | `dirty` | `direct` | `LOGS/raw/dirty_direct.jsonl` |
| 4 | `dirty` | `mcp` | `LOGS/raw/dirty_mcp.jsonl` |
| 5 | `multi_sunny` | `direct` | `LOGS/raw/multi_sunny_direct.jsonl` |
| 6 | `multi_sunny` | `mcp` | `LOGS/raw/multi_sunny_mcp.jsonl` |
| 7 | `multi_dirty` | `direct` | `LOGS/raw/multi_dirty_direct.jsonl` |
| 8 | `multi_dirty` | `mcp` | `LOGS/raw/multi_dirty_mcp.jsonl` |

### Schritt für Schritt

**Für jeden Lauf: CONFIG anpassen und Runner starten.**

Beispiel für Lauf 1 (`sunny` + `direct`):
```python
# In benchmark/runner.py:
CONFIG = {
    "case":       "sunny",
    "modus":      "direct",
    "iterations": 100,
    "model":      "claude-sonnet-4-20250514",
}
```
```bash
python -m benchmark.runner
```

> **Hinweis (Windows, venv nicht aktiviert):** `.\venv\Scripts\python.exe -m benchmark.runner`

Dann für Lauf 2 `"modus": "mcp"` setzen, usw.

### Alle 4 Szenarien auf einmal (automatisch)

Statt jeden Lauf manuell zu starten, kann `run_all()` verwendet werden:

```python
# In benchmark/runner.py, Zeile 308:
if __name__ == "__main__":
    runner = BenchmarkRunner(iterations=CONFIG["iterations"], model_name=CONFIG["model"])
    runner.run_all()   # <-- statt runner.run_selected()
```

```bash
python -m benchmark.runner
```

### Auswertung nach allen Läufen

```bash
# Einzelne JSONL-Datei bewerten (falls nötig, sonst passiert das automatisch):
python -m benchmark.judge --file sunny_direct

# Alle Dateien auf einmal:
python -m benchmark.judge

# Zusammenfassung anzeigen (CSV):
# LOGS/summaries/benchmark_summary.csv
```


## Evaluator — Deterministische Qualitätsbewertung

Der Benchmark läuft in **zwei Phasen**:

**Phase 1 — Datenmessung** (`benchmark/runner.py`)
Der Agent führt die Aufgabe aus. Latenz, aufgerufene Tools und die finale LLM-Antwort werden geloggt. Die Felder `judge_score` und `judge_reason` bleiben zunächst `null`, damit die Laufzeit-Messung sauber bleibt.

**Phase 2 — Qualitätsbewertung** (`benchmark/judge.py`)
Ein regelbasierter Evaluator prüft die gespeicherte Antwort gegen bekannte Ground-Truth-Fakten der Mock-API. Jeder Check ist eine explizite, dokumentierte Regel:

| Szenario | Checks |
|---|---|
| `sunny` / `dirty` | Enthält die Antwort: einen Produktnamen, "Smartphone" als zweites Item, Lagerbestand "25"? |
| `multi_sunny` / `multi_dirty` | Enthält die Antwort: einen Produktnamen, Lagerbestand "15" (Tablet), Kundenname "Bob", Rabatt "10%" oder "0.1", Bestellbestätigung? |

Das Ergebnis ist ein `judge_score` (0.0-1.0) als Anteil bestehender Checks, sowie eine `judge_reason` die zeigt welche Checks fehlgeschlagen sind.

> **Warum keine modell-basierte Evaluation (LLM-as-a-Judge)?** Da das Modell gleichzeitig Proband und Richter wäre, entstünde ein methodischer Zirkelschluss. Der deterministische Ansatz ist reproduzierbar, transparent und akademisch vertretbar - jeder Score ist auf einzelne Pass/Fail-Checks zurückführbar.

```bash
# Alle JSONL-Dateien bewerten
python -m benchmark.judge

# Nur eine bestimmte Datei bewerten
python -m benchmark.judge --file sunny_direct

# Trockenlauf (keine Schreiboperationen)
python -m benchmark.judge --dry-run
```

---

## Log-Format

Jeder Run schreibt eine JSONL-Zeile nach `LOGS/raw/`:

```json
{
  "run_id": 42,
  "approach": "mcp",
  "scenario": "dirty",
  "timestamp": "2026-02-19T14:30:05.123456+00:00",
  "metrics": {
    "t_e2e_ms": 1245.8,
    "t_protocol_overhead_ms": 18.2,
    "t_api_logic_ms": 55.0
  },
  "execution_details": {
    "tools_called": ["get_inventory_mcp", "get_stock_mcp"],
    "tool_call_valid": true,
    "api_status_codes": [200, 200],
    "exception_caught": false,
    "llm_response": "The second item is a Smartphone with 25 units in stock."
  },
  "evaluation": {
    "success": true,
    "judge_score": null,
    "judge_reason": null
  }
}
```

---

## API-Endpunkte (Mock)

| Route | Sunny | Dirty |
|---|---|---|
| `GET /*/products` | Sauber | Fehlende Felder, Typ-Fehler, 500er |
| `GET /*/stock/{id}` | `{"product_id": 1, "stock": 10}` | Liste oder dict, String-ID |
| `POST /*/orders` | Validiert, gibt `Order` zurück | Inkonsistente Schlüssel (`id` vs `order_id`) |
| `GET /*/customers/{id}` | Sauber | `name` → `customer_name`, fehlende `email` |
| `GET /*/discounts?product_id=` | Float | `"10%"` String oder `"none"` |
