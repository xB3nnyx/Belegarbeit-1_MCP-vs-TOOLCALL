import time
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def get_timestamp() -> int:
    """Returns the current time as a Unix timestamp in nanoseconds."""
    return time.time_ns()


# ---------------------------------------------------------------------------
# RunLogger — one instance per benchmark run, writes one structured record
# ---------------------------------------------------------------------------

class RunLogger:
    """
    Accumulates all timing and metadata for a single benchmark run and
    writes one fully-structured JSONL record to LOGS/raw/ when commit() is called.

    Expected JSONL schema (matches LOGGING_CONCEPT.md):
    {
        "run_id":    int,
        "approach":  "direct" | "mcp",
        "scenario":  "sunny" | "dirty" | "multi_sunny" | "multi_dirty",
        "timestamp": ISO-8601 string (UTC),
        "metrics": {
            "t_e2e_ms":              float,   # total client → response latency
            "t_protocol_overhead_ms": float,  # sum of transport gaps per tool call
            "t_api_logic_ms":         float   # sum of in-tool processing time
        },
        "execution_details": {
            "tools_called":     list[str],
            "tool_call_valid":  bool,          # did LLM honour every tool schema?
            "api_status_codes": list[int],
            "exception_caught": bool,
            "llm_response":     str | null
        },
        "evaluation": {
            "success":      bool,
            "judge_score":  float | null,      # 0.0-1.0, set by automated evaluator later
            "judge_reason": str  | null
        }
    }
    """

    def __init__(self, run_id: int, approach: str, scenario: str):
        self.run_id   = run_id
        self.approach = approach   # "direct" or "mcp"
        self.scenario = scenario   # "sunny", "dirty", "multi_sunny", "multi_dirty"

        self._log_dir  = Path("LOGS/raw")
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._log_file = self._log_dir / f"{scenario}_{approach}.jsonl"

        # Timing buckets (nanosecond walls)
        self._t_client_sent: Optional[int] = None
        self._t_client_recv: Optional[int] = None
        self._tool_spans: list[Dict[str, Any]] = []   # [{name, sent_ns, recv_ns, api_start_ns, api_end_ns}]

        # Execution metadata
        self._tools_called:     list[str]  = []
        self._tool_call_valid:  bool       = True
        self._api_status_codes: list[int]  = []
        self._exception_caught: bool       = False
        self._llm_response:     Optional[str] = None

        # Evaluation (populated externally, e.g. by benchmark judge)
        self.judge_score:  Optional[float] = None
        self.judge_reason: Optional[str]   = None

    # ------------------------------------------------------------------
    # Timing events — call these from runner and tool wrappers
    # ------------------------------------------------------------------

    def mark_request_sent(self):
        """Call just before handing the prompt to the AgentExecutor."""
        self._t_client_sent = get_timestamp()

    def mark_response_received(self, llm_response: Optional[str] = None,
                               exception: Optional[Exception] = None):
        """Call immediately after AgentExecutor returns (or raises)."""
        self._t_client_recv = get_timestamp()
        if llm_response is not None:
            self._llm_response = llm_response
        if exception is not None:
            self._exception_caught = True

    def mark_tool_request_sent(self, tool_name: str):
        """
        Call just before the transport layer delivers the call to the tool.
        Returns a span-handle dict used by mark_tool_request_received().
        """
        span = {"name": tool_name, "sent_ns": get_timestamp(),
                "recv_ns": None, "api_start_ns": None, "api_end_ns": None}
        self._tool_spans.append(span)
        self._tools_called.append(tool_name)
        return span

    def mark_tool_request_received(self, span: Dict[str, Any]):
        """Call at the entry point of the tool function (start of API logic)."""
        span["recv_ns"]      = get_timestamp()
        span["api_start_ns"] = span["recv_ns"]

    def mark_tool_response_sent(self, span: Dict[str, Any],
                                status_code: Optional[int] = None,
                                valid: bool = True):
        """Call just before the tool function returns its value."""
        span["api_end_ns"] = get_timestamp()
        if status_code is not None:
            self._api_status_codes.append(status_code)
        if not valid:
            self._tool_call_valid = False

    # ------------------------------------------------------------------
    # Commit — assemble and write the structured record
    # ------------------------------------------------------------------

    def commit(self):
        """Compute derived metrics and append one JSON line to the log file."""
        t_e2e_ms = 0.0
        if self._t_client_sent and self._t_client_recv:
            t_e2e_ms = (self._t_client_recv - self._t_client_sent) / 1_000_000

        # Refined timing: Calculate the UNION of spans to handle parallel calls.
        # This prevents t_protocol_overhead_ms from exceeding t_e2e_ms.
        protocol_intervals = []
        api_intervals      = []

        for span in self._tool_spans:
            if span["sent_ns"] and span["recv_ns"]:
                protocol_intervals.append((span["sent_ns"], span["recv_ns"]))
            if span["api_start_ns"] and span["api_end_ns"]:
                api_intervals.append((span["api_start_ns"], span["api_end_ns"]))

        def union_duration_ms(intervals):
            if not intervals: return 0.0
            # Sort by start time
            sorted_ints = sorted(intervals, key=lambda x: x[0])
            merged = []
            if not sorted_ints: return 0.0
            
            curr_start, curr_end = sorted_ints[0]
            for next_start, next_end in sorted_ints[1:]:
                if next_start <= curr_end:
                    curr_end = max(curr_end, next_end)
                else:
                    merged.append((curr_start, curr_end))
                    curr_start, curr_end = next_start, next_end
            merged.append((curr_start, curr_end))
            
            total_ns = sum((e - s) for s, e in merged)
            return total_ns / 1_000_000

        t_protocol_overhead_ms = union_duration_ms(protocol_intervals)
        t_api_logic_ms         = union_duration_ms(api_intervals)

        record = {
            "run_id":    self.run_id,
            "approach":  self.approach,
            "scenario":  self.scenario,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metrics": {
                "t_e2e_ms":               round(t_e2e_ms, 3),
                "t_protocol_overhead_ms": round(t_protocol_overhead_ms, 3),
                "t_api_logic_ms":         round(t_api_logic_ms, 3),
            },
            "execution_details": {
                "tools_called":     self._tools_called,
                "tool_call_valid":  self._tool_call_valid,
                "api_status_codes": self._api_status_codes,
                "exception_caught": self._exception_caught,
                "llm_response":     self._llm_response,
            },
            "evaluation": {
                "success":      not self._exception_caught and self._tool_call_valid,
                "judge_score":  self.judge_score,
                "judge_reason": self.judge_reason,
            },
        }

        with open(self._log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

        return record


# ---------------------------------------------------------------------------
# Legacy flat-event logger — kept for backwards compatibility
# ---------------------------------------------------------------------------

class BenchmarkLogger:
    """
    Legacy logger that writes one JSON line per event.
    Kept for any code that has not yet been migrated to RunLogger.
    """

    def __init__(self, scenario_name: str):
        self.scenario_name = scenario_name
        self.log_dir  = Path("LOGS/raw")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / f"{scenario_name}.jsonl"

    def log_event(self, event_type: str, data: dict):
        entry = {
            "timestamp_ns": get_timestamp(),
            "datetime":     datetime.now(timezone.utc).isoformat(),
            "event_type":   event_type,
            "scenario":     self.scenario_name,
            **data,
        }
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
