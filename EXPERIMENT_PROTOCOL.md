# Experiment-Protokoll

Das Experiment wird in vier Phasen unterteilt. Jede Phase wird sowohl für **Ansatz A (Direct)** als auch **Ansatz B (MCP)** durchgeführt (n=100 pro Phase).

## Phase 1: Sunny Case (Ein Endpunkt)
- **API-Zustand:** Perfekt dokumentiert, schnelle Antwortzeiten, valide Datentypen.
- **Ziel:** Messung der Basis-Latenz und des Protokoll-Overheads von MCP unter Idealbedingungen.

## Phase 2: Dirty Case (Ein Endpunkt)
- **API-Zustand:** Inkonsistente Schemata, fehlende Beschreibungen in der API, gelegentliche 500er Fehler.
- **Ziel:** Evaluation der Robustheit. Kann das MCP-Schema (Wrapper) die "Dirty API" besser vor dem LLM verbergen als der direkte Call? -> Also kann das LLM zufriedenstellend mit einer solchen API über MCP arbeiten? Ist Tool-Calling in dem Fall besser?

## Phase 3: Multiple-Sunny (Fünf Endpunkte)
- **API-Zustand:** Fünf verschiedene, saubere Endpunkte (z.B. Lager, Preise, Versand, Kunden, Rabatte).
- **Ziel:** Messung der Skalierbarkeit. Steigt die Latenz bei MCP exponentiell oder linear? Kann MCP die richtigen Endpunkte ansteuern? Ist der Mehraufwand beim Tool-Calling hier lohnend?

## Phase 4: Multiple-Dirty (Fünf Endpunkte)
- **API-Zustand:** Mix aus unsauberen Endpunkten und komplexen Abhängigkeiten.
- **Ziel:** Stress-Test für die LLM-Orchestrierung. Ab wann "verlieren" die Agenten den Faden? Kann die MCP-Architektur dem Standhalten? Kann die Tool-Calling dem Standhalten? 

## 5. Datenerfassung und Evaluation

Zur Sicherstellung der wissenschaftlichen Validität folgt die Datenerfassung einem strikten Protokoll. Jede Interaktion zwischen dem LLM-Agenten und den Tools wird in Echtzeit protokolliert.

- **Detailliertes Logging-Schema:** Siehe [LOGGING_CONCEPT.md](./LOGGING_CONCEPT.md) für die genaue Definition der Zeitstempel und Datenfelder.
- **Automatisierung:** Die Messung erfolgt automatisiert über den `benchmark/runner.py`. Es werden pro Szenario 100 Iterationen durchgeführt, um statistische Ausreißer (z.B. durch Netzwerk-Schwankungen der LLM-API) zu minimieren.
- **Datenintegrität:** Die Logs werden im `/LOGS/raw/` Verzeichnis als JSON-Lines gespeichert, um eine einfache Nachverarbeitung mittels Python/Pandas zu ermöglichen.