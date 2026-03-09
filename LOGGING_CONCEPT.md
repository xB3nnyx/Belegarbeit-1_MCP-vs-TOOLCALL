# Logging-Konzept & Datenstruktur

Dieses Dokument beschreibt die systematische Datenerfassung während der Experimente. Ziel ist die lückenlose Nachvollziehbarkeit der Performance- und Robustheitsmetriken.

> **Warum kein AI-as-a-Judge?** Da das Modell gleichzeitig Proband und Richter wäre, entstünde ein methodischer Zirkelschluss. Der deterministische Ansatz ist reproduzierbar, transparent und akademisch vertretbar - jeder Score ist auf einzelne Pass/Fail-Checks zurückführbar.

## 1. Ordnerstruktur
Die Logs werden im Root-Verzeichnis unter `/LOGS` gespeichert und nach Szenarien getrennt.

```text
/LOGS
├── /raw                        # Unverarbeitete Einzelmessungen (JSONL)
│   ├── sunny_direct.jsonl      # 100 Runs: Ein Endpunkt, sauber
│   ├── sunny_mcp.jsonl         # 100 Runs: Ein Endpunkt, MCP-Wrapper
│   ├── dirty_direct.jsonl      # 100 Runs: Ein Endpunkt, unsauber
│   ├── dirty_mcp.jsonl         # ...
│   ├── multi_sunny_direct.jsonl
│   └── ...
└── /summaries                  # Aggregierte Daten für die Auswertung
    └── results_matrix.csv      # Vergleichstabelle (Mittelwerte, Fehler)
```

## 2. Erfasste Metriken (Data Points)

Um die Hypothesen zu Latenz, Overhead und Robustheit prüfen zu können, wird jeder Testlauf (Run) mit folgenden Datenpunkten erfasst:

| Kategorie | Feld | Datentyp | Beschreibung |
| :--- | :--- | :--- | :--- |
| **Identifikation** | `run_id` | Integer | Eindeutige ID des Testlaufs innerhalb des Szenarios (1-100). |
| | `approach` | String | `direct` (LangChain Native) oder `mcp` (FastMCP Wrapper). |
| | `scenario` | String | `sunny`, `dirty`, `multi_sunny` oder `multi_dirty`. |
| **Performance** | `t_e2e_ms` | Float | Gesamte Latenz vom Absenden des Prompts bis zur finalen Antwort. |
| | `t_protocol_overhead_ms`| Float | Zeitdifferenz, die durch die MCP-Schicht (JSON-RPC) entsteht. |
| | `t_api_logic_ms` | Float | Reine Rechenzeit innerhalb der Mock-API (Business Logic). |
| **Robustheit** | `tool_call_valid` | Boolean | Hat das LLM das Tool-Schema korrekt eingehalten? |
| | `api_status_codes` | List[Int]| HTTP Status Codes der API-Aufrufe (z.B. [200, 404]). |
| | `exception_caught` | Boolean | Wurde ein Laufzeitfehler durch den Code abgefangen? |
| **Qualität** | `judge_score` | Float | Bewertung der Antwortqualität durch deterministische Regeln (Skala 0.0 - 1.0). |
| | `judge_reason` | String | Kurze Begründung des Scores durch den Evaluator. |

---

## 3. Beispiel eines Log-Eintrags (JSONL)

Jeder Testlauf schreibt eine Zeile in die entsprechende `.jsonl`-Datei. Dies ermöglicht eine performante Speicherung und eine einfache spätere Analyse mit Python/Pandas.

```json
{
  "run_id": 42,
  "approach": "mcp",
  "scenario": "dirty",
  "timestamp": "2026-02-11T14:30:05.123456",
  "metrics": {
    "t_e2e_ms": 1245.8,
    "t_protocol_overhead_ms": 18.2,
    "t_api_logic_ms": 55.0
  },
  "execution_details": {
    "tools_called": ["get_inventory_mcp"],
    "tool_call_valid": true,
    "api_status_codes": [200],
    "exception_caught": false,
    "llm_response": "The inventory contains..."
  },
  "evaluation": {
    "success": true,
    "judge_score": 1.0,
    "judge_reason": "All checks passed"
  }
}

 