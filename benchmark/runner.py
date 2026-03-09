import os
import json
import asyncio
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv
from typing import List, Dict, Any
from pydantic import create_model

# LangChain 1.x API
from langchain.agents import create_agent
from langchain_anthropic import ChatAnthropic
from langchain_core.tools import StructuredTool

# MCP
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Project
from log_utils.logger import RunLogger
from approaches.direct_calling import DirectCallingApproach
from benchmark.judge import score_file

load_dotenv()

# ---------------------------------------------------------------------------
# CONFIG — adjust before each run
# ---------------------------------------------------------------------------
CONFIG = {
    "case":       "multi_dirty",   # "sunny" | "dirty" | "multi_sunny" | "multi_dirty"
    "modus":      "mcp",  # "direct" | "mcp"
    "iterations": 100,
    "model":      "claude-sonnet-4-20250514",
}
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Scenario definitions
# ---------------------------------------------------------------------------

def _api_mode(scenario: str) -> str:
    return "dirty" if "dirty" in scenario else "sunny"

# IMPORTANT: sunny/dirty should have the same queries to be comparable
SCENARIO_QUERIES = {
    "sunny": (
        "What products are in the inventory and what is the stock of the second item?"
    ),
    "dirty": (
        "What products are in the inventory and what is the stock of the second item?"
    ),
    "multi_sunny": (
        "Give me a full sales summary using all available tools: "
        "1) List all products. "
        "2) Check the stock of product with id 3. "
        "3) Look up the customer with id 2. "
        "4) Find the discount for product with id 1. "
        "5) Place an order for customer 1 buying 1 unit of product 2. "
        "Summarise all results in a structured way."
    ),
    "multi_dirty": (
        "Give me a full sales summary using all available tools: "
        "1) List all products. "
        "2) Check the stock of product with id 3. "
        "3) Look up the customer with id 2. "
        "4) Find the discount for product with id 1. "
        "5) Place an order for customer 1 buying 1 unit of product 2. "
        "Summarise all results in a structured way."
    ),
}


class BenchmarkRunner:
    """
    Orchestrates N iterations per scenario.
    Uses StructuredTool to ensure proper schemas for LLMs.
    Injects mode automatically into each tool call.
    """

    def __init__(self, iterations: int = 100, model_name: str = "claude-sonnet-4-20250514"):
        self.iterations  = iterations
        self.model_name  = model_name
        self.results_dir = Path("LOGS/summaries")
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.llm = ChatAnthropic(model=self.model_name, temperature=0)

    # ------------------------------------------------------------------
    # Direct benchmark
    # ------------------------------------------------------------------

    def run_direct_benchmark(self, scenario: str):
        print(f"--- Starting Direct Benchmark: {scenario} ---")
        mode    = _api_mode(scenario)
        query   = SCENARIO_QUERIES[scenario]
        approach = DirectCallingApproach(scenario)

        SYSTEM_PROMPT = (
            "You are a helpful assistant for an online shop. "
            "Use the available tools to answer questions. "
            "Provide accurate information based on tool outputs."
        )

        for i in range(1, self.iterations + 1):
            print(f"  Iteration {i}/{self.iterations}...")
            run_log = RunLogger(run_id=i, approach="direct", scenario=scenario)

            # Inject context (mode and iteration) into the direct tools
            approach.set_context(run_log, mode, i)

            agent = create_agent(self.llm, approach.tools, system_prompt=SYSTEM_PROMPT)

            run_log.mark_request_sent()
            try:
                result = agent.invoke({"messages": [("user", query)]})
                output = result["messages"][-1].content
                run_log.mark_response_received(llm_response=output)
            except Exception as e:
                run_log.mark_response_received(exception=e)

            run_log.commit()

        # Automatically score the results after the iterations are done
        log_file = Path(f"LOGS/raw/{scenario}_direct.jsonl")
        if log_file.exists():
            print(f"  Scoring results for {scenario}_direct...")
            score_file(log_file)

    # ------------------------------------------------------------------
    # MCP benchmark
    # ------------------------------------------------------------------

    async def run_mcp_benchmark(self, scenario: str):
        print(f"--- Starting MCP Benchmark: {scenario} ---")
        mode  = _api_mode(scenario)
        query = SCENARIO_QUERIES[scenario]

        server_params = StdioServerParameters(
            command="python",
            args=[str(Path("approaches/mcp_wrapper.py").absolute())],
            env={**os.environ, "BENCHMARK_SCENARIO": scenario},
        )

        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                mcp_tools_list = await session.list_tools()

                for i in range(1, self.iterations + 1):
                    print(f"  Iteration {i}/{self.iterations}...")
                    run_log = RunLogger(run_id=i, approach="mcp", scenario=scenario)

                    final_tools: List[StructuredTool] = []
                    for m_tool in mcp_tools_list.tools:
                        
                        # Dynamically create a Pydantic model for the tool arguments
                        # but EXCLUDE 'mode' and 'iteration'
                        
                        properties = m_tool.inputSchema.get("properties", {})
                        fields = {}
                        for prop_name, prop_info in properties.items():
                            if prop_name in ["mode", "iteration"]:
                                continue
                            
                            # Map JSON schema types to Python types
                            type_map = {"string": str, "integer": int, "number": float, "boolean": bool}
                            p_type = type_map.get(prop_info.get("type"), Any)
                            fields[prop_name] = (p_type, ... if prop_name in m_tool.inputSchema.get("required", []) else None)
                        
                        ArgsModel = create_model(f"{m_tool.name}Args", **fields)

                        async def call_mcp_tool_wrapper(name=m_tool.name, **kwargs):
                            span = run_log.mark_tool_request_sent(name)
                            # Inject mode so the MCP tool knows which API endpoints to call
                            kwargs["mode"] = mode

                            try:
                                resp = await session.call_tool(name, kwargs)
                                # mark_tool_request_received AFTER the full round-trip —
                                # this means t_protocol_overhead = full MCP transport + execution,
                                # which is the honest measurement from the client's perspective.
                                run_log.mark_tool_request_received(span)
                                raw = "".join(
                                    c.text for c in resp.content if hasattr(c, "text")
                                )

                                # Parse the JSON envelope added by mcp_wrapper.py to
                                # extract the HTTP status code for logging.
                                status_code = None
                                result_text = raw
                                try:
                                    parsed = json.loads(raw)
                                    if "_status" in parsed:
                                        status_code = parsed["_status"]
                                        result_text = str(parsed.get("result", ""))
                                except (json.JSONDecodeError, TypeError):
                                    pass  # non-JSON response, return as-is

                                valid = status_code is None or status_code in (200, 201)
                                run_log.mark_tool_response_sent(span, status_code=status_code, valid=valid)
                                return result_text
                            except Exception as e:
                                run_log.mark_tool_request_received(span)
                                run_log.mark_tool_response_sent(span, valid=False)
                                return f"MCP Tool Error: {e}"

                        t = StructuredTool(
                            name=m_tool.name,
                            func=None,
                            coroutine=call_mcp_tool_wrapper,
                            description=m_tool.description,
                            args_schema=ArgsModel
                        )
                        final_tools.append(t)

                    SYSTEM_PROMPT = (
                        "You are a helpful assistant for an online shop. "
                        "Use the available MCP tools to answer questions. "
                        "Provide accurate information based on tool outputs."
                    )
                    agent = create_agent(self.llm, final_tools, system_prompt=SYSTEM_PROMPT)

                    run_log.mark_request_sent()
                    try:
                        result = await agent.ainvoke({"messages": [("user", query)]})
                        output = result["messages"][-1].content
                        run_log.mark_response_received(llm_response=output)
                    except Exception as e:
                        run_log.mark_response_received(exception=e)

                    run_log.commit()

        # Automatically score the results after the iterations are done
        log_file = Path(f"LOGS/raw/{scenario}_mcp.jsonl")
        if log_file.exists():
            print(f"  Scoring results for {scenario}_mcp...")
            score_file(log_file)

    # ------------------------------------------------------------------
    # Entry points
    # ------------------------------------------------------------------

    def run_selected(self):
        scenario = CONFIG["case"]
        modus    = CONFIG["modus"]

        if modus == "all":
            self.run_all()
        elif modus == "direct":
            self.run_direct_benchmark(scenario)
        elif modus == "mcp":
            asyncio.run(self.run_mcp_benchmark(scenario))

    def run_all(self):
        for scenario in ["sunny", "dirty", "multi_sunny", "multi_dirty"]:
            self.run_direct_benchmark(scenario)
            asyncio.run(self.run_mcp_benchmark(scenario))
        self.aggregate_results()

    def aggregate_results(self):
        print("--- Aggregating Results ---")
        rows    = []
        raw_dir = Path("LOGS/raw")
        if not raw_dir.exists(): return

        for log_file in raw_dir.glob("*.jsonl"):
            with open(log_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        rec = json.loads(line)
                        if "run_id" not in rec: continue
                        m  = rec.get("metrics", {})
                        ed = rec.get("execution_details", {})
                        ev = rec.get("evaluation", {})
                        rows.append({
                            "scenario_approach":      f"{rec.get('scenario')}_{rec.get('approach')}",
                            "run_id":                 rec.get("run_id"),
                            "approach":               rec.get("approach"),
                            "scenario":               rec.get("scenario"),
                            "t_e2e_ms":               m.get("t_e2e_ms"),
                            "t_protocol_overhead_ms": m.get("t_protocol_overhead_ms"),
                            "t_api_logic_ms":         m.get("t_api_logic_ms"),
                            "tools_called":           ", ".join(ed.get("tools_called", [])),
                            "api_status_codes":       ", ".join(map(str, ed.get("api_status_codes", []))),
                            "success":                ev.get("success"),
                            "judge_score":            ev.get("judge_score"),
                            "judge_reason":           ev.get("judge_reason"),
                        })
                    except: continue

        if not rows: return
        df = pd.DataFrame(rows)
        # Use LOGS/summaries directory and semicolon separator for Excel
        out_dir = Path("LOGS/summaries")
        out_dir.mkdir(parents=True, exist_ok=True)
        
        df.to_csv(out_dir / "results_detailed.csv", index=False, sep=";")
        summary = df.groupby("scenario_approach")[["t_e2e_ms", "t_protocol_overhead_ms", "t_api_logic_ms", "judge_score"]].mean().round(3).reset_index()
        print(summary.to_string(index=False))
        summary.to_csv(out_dir / "benchmark_summary.csv", index=False, sep=";")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run the MCP vs Direct Calling benchmark.")
    parser.add_argument("--iterations", type=int, default=CONFIG["iterations"], help="Number of times to run")
    parser.add_argument("--case", type=str, default=CONFIG["case"], help="Scenario to run")
    parser.add_argument("--modus", type=str, default=CONFIG["modus"], help="'direct', 'mcp', or 'all'")
    args = parser.parse_args()

    CONFIG["iterations"] = args.iterations
    CONFIG["case"] = args.case
    CONFIG["modus"] = args.modus

    runner = BenchmarkRunner(iterations=CONFIG["iterations"], model_name=CONFIG["model"])
    if args.modus == "aggregate":
        runner.aggregate_results()
    else:
        runner.run_selected()
