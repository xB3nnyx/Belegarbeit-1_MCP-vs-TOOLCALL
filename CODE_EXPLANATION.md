# Code-Erklärung: MCP vs. Direct Tool-Calling Benchmark

Dieses Dokument beschreibt die Architektur und die einzelnen Komponenten des Repositories, um das wissenschaftliche Experiment nachvollziehbar zu machen.

## 1. Ordnerstruktur im Überblick

```text
/
├── api_service/       # Die "Mock-API" (Single Source of Truth)
├── approaches/        # Die zwei zu vergleichenden Aufruf-Methoden
├── benchmark/         # Automatisierung des Experimentablaufs
├── logging/           # Zentrales Mess-Modul
└── LOGS/              # Datenspeicher für Ergebnisse
```

---

## 2. Detaillierte Komponenten-Beschreibung

### `/api_service`
Dies ist der Kern des Projekts. Hier wird die Geschäftslogik simuliert.
- **`main.py`**: Enthält eine FastAPI-App mit verschiedenen Endpunkten.
  - **Sunny-Modus**: Liefert perfekte Daten (Pydantic-validiert), klare Beschreibungen.
  - **Dirty-Modus**: Simuliert die Realität unsauberer APIs (Preise als Strings, fehlende Felder, sporadische 500er Fehler).
  - *Zweck*: Trennung der Logik von der Zugriffsmethode gemäß Best Practices für modulare Softwarearchitektur.

### `/approaches`
Hier liegen die beiden "Gegner" des Benchmarks.
- **`direct_calling.py`**:
  - Nutzt LangChain `@tool` Decorators.
  - Das LLM spricht die API direkt an.
  - Loggt den Eingang des Requests direkt im Tool-Code.
- **`mcp_wrapper.py`**:
  - Implementiert einen **FastMCP-Server**.
  - Fungiert als "Übersetzer" oder "Wrapper" zwischen LLM und API.
  - Bietet die Möglichkeit, "Dirty"-Daten vor dem LLM zu bereinigen, bevor sie zurückgegeben werden.

### `/benchmark`
Die Schaltzentrale für die Durchführung.
- **`runner.py`**:
  - **Konfiguration**: Erlaubt oben im Code das Festlegen von `case` (Sunny/Dirty) und `modus` (Direct/MCP).
  - **Integration**: Nutzt `ChatAnthropic` (Claude-Sonnet-4) und LangChain `AgentExecutor`, um echte KI-Interaktionen durchzuführen.
  - **Ablauf**: Führt die Schleife von n-Iterationen (Standard: 100) aus und sorgt dafür, dass jeder Schritt zeitlich erfasst wird.

### `/logging`
- **`logger.py`**:
  - Nutzt `time.perf_counter_ns()`, um Nanosekunden-Präzision zu erreichen. 
  - Schreibt JSONL-Dateien in `/LOGS/raw`.
  - Stellt sicher, dass die drei geforderten Zeitstempel (Absendung, Eingang am Tool, Erhalt der Antwort) korrekt zugeordnet werden können.

---

## 3. Workflow des Experiments
1. **API Start**: Der `api_service` läuft als eigener Prozess.
2. **Runner Start**: Im `runner.py` wird die Konfiguration gewählt.
3. **LLM Loop**: Das LLM erhält eine Aufgabe (z.B. "Checke Lagerbestand").
4. **Messung**: Der Logger zieht bei jedem Schritt die Zeit.
5. **Aggregation**: Nach Beendigung werden die JSONL-Files zu einer statistischen Matrix (`results_matrix.csv`) zusammengefasst.
