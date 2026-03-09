# 4. Implementierung & Versuchsaufbau

Dieser Abschnitt beschreibt die technische Umsetzung des Benchmarks sowie das methodische Vorgehen bei der Durchführung des Experiments.

## 4.1 Technische Versuchsumgebung

Die gesamte Testumgebung wurde in **Python 3.11+** realisiert. Folgende Schlüssel-Technologien wurden verwendet:

*   **Large Language Model (Proband):** Claude-Sonnet-4 (`claude-sonnet-4-20250514`).
*   **Orchestrierung:** **LangChain** (v0.3+) für die Agenten-Logik und Tool-Verwaltung.
*   **Model Context Protocol (MCP):** Realisierung über das **FastMCP-SDK** (Python).
*   **Zusätzliche Bibliotheken:** `pydantic` für die Datenvalidierung, `fastapi` für den API-Service, `pandas` für die Datenaggregation.

## 4.2 Architektur der Integrationspfade

Das Experiment vergleicht zwei grundlegende Integrationsparadigmen:

*   **Referenz-API (Native/Direct):** Der Agent nutzt die native Anthropic-API. Die Tool-Spezifikationen werden direkt im LangChain-Framework hinterlegt.
*   **FastMCP-Server (MCP):** Ein dedizierter MCP-Server fungiert als Abstraktionsschicht. Er deklariert Tools autonom und normalisiert die Kommunikation zwischen Host und API.

## 4.3 Definition der Test-Szenarien

Um die Robustheit und Skalierbarkeit zu prüfen, wurden vier Szenarien definiert (n = 100 Iterationen pro Pfad):

### 4.3.1 Szenario 1: Sunny Case (Optimale Metadaten)
*   **Beschreibung:** Ein einzelner Endpunkt mit perfekter Dokumentation.
*   **Charakteristika:** Klare Schemata, `product_id` als `int`, vollständige Pydantic-Beschreibungen.

### 4.3.2 Szenario 2: Dirty Case (Lückenhafte Dokumentation & Chaos)
*   **Beschreibung:** Ein Endpunkt mit simulierten Qualitätsmängeln und dynamischem API-Chaos.
*   **Konkrete Fehlerbilder:**
    *   **Vage Beschreibungen:** Docstrings wie "Gets stuff" statt technischer Erläuterungen.
    *   **Inkonsistente Identifier:** Wechselnde Keys (mal `pid`, mal `product_id`).
    *   **Typ-Chaos:** Preise werden als Strings geliefert (z. B. `"19.99 EUR"`) statt als `float`.
    *   **Schema Chaos (5%):** Plötzliche Änderung kompletter Datenstrukturen (z.B. tiefe Verschachtelungen, völlig neue Key-Namen wie `inventory_qty`).
    *   **Status Code Lying (5%):** Die API lügt über den Erfolg (HTTP 200 mit Fehlertext im Body, oder HTTP 500 mit gültigen Daten).
    *   **Server-Fehler:** Eine künstlich induzierte Fehlerrate von 15 % (echter HTTP 500).

### 4.3.3 Szenario 3: Multi Sunny Case (Orchestrierung)
*   **Beschreibung:** Komplexe Orchestrierung mehrerer Endpunkte unter Idealbedingungen.
*   **Ablauf:** Produktliste abrufen → Lagerbestand prüfen (ID 3) → Kundendaten laden (ID 2) → Rabatt prüfen (ID 1) → Bestellung aufgeben (Kunde 1, Produkt 2).

### 4.3.4 Szenario 4: Multi Dirty Case (Stress-Test)
*   **Beschreibung:** Die Orchestrierung von Szenario 3, jedoch mit den Qualitätsmängeln und dem API-Chaos aus Szenario 2 bei jedem Schritt. Herausforderung ist die Fehlererkennung und Fehlerfortpflanzung innerhalb der Kette.

## 4.4 Evaluierungskriterien

Die Bewertung erfolgt dreidimensional:

1.  **Quantitativ (Performance):**
    *   **E2E-Latenz:** Gesamtdauer des Durchlaufs.
2.  **Qualitativ (Korrektheit & Robustheit):**
    *   **Multi-Factor Judge Score [0.0 - 1.0]:**
        *   **Baseline:** Gelingt die Kernaufgabe trotz Chaos?
        *   **Robustness Bonus:** Erkennt das Modell "Status Code Lying" oder "Schema Chaos" und weist den Nutzer darauf hin (+0.1 pro Check)?
3.  **Developer Experience:** Vergleich der **Lines of Code (LOC)** für die Integration und der Konfigurationskomplexität (Glue-Code Aufwand).

## 4.5 Durchführungsmethodik

Das Experiment folgt einem strikten Protokoll (n=100 pro Pfad/Szenario, insgesamt 800 Messpunkte). Zur Sicherstellung der wissenschaftlichen Validität erfolgt eine **Ausreißer-Bereinigung** (Statistical Scrubbing), um Netzwerk-Ausreißer der LLM-API abzufangen und den reinen Protokoll-Overhead isoliert zu betrachten.
