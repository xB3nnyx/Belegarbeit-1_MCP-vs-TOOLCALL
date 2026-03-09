import contextvars
import requests
from langchain.tools import tool
from typing import Optional
from log_utils.logger import RunLogger

# ---------------------------------------------------------------------------
# ContextVar — ensures context is preserved across thread boundaries (LangGraph).
# ---------------------------------------------------------------------------
_run_log_var = contextvars.ContextVar("run_log", default=None)
_mode_var    = contextvars.ContextVar("mode", default="sunny")


def _get_ctx() -> tuple[Optional[RunLogger], str]:
    """Return (run_log, mode) from context variables."""
    return _run_log_var.get(), _mode_var.get()


# ---------------------------------------------------------------------------
# Tools — metadata (run_log and mode) is injected via set_context()
# ---------------------------------------------------------------------------

@tool
def get_inventory_direct() -> str:
    """
    Fetches the current product inventory directly from the API.
    Returns a list of products with id, name, price and stock.
    """
    rl, mode = _get_ctx()
    span = rl.mark_tool_request_sent("get_inventory_direct") if rl else None
    url = f"http://localhost:8000/{mode}/products"
    try:
        if span:
            rl.mark_tool_request_received(span)
        response = requests.get(url, timeout=5)
        data = response.json()
        if span:
            rl.mark_tool_response_sent(span, status_code=response.status_code,
                                       valid=response.status_code in (200, 201))
        return str(data)
    except Exception as e:
        if span:
            rl.mark_tool_response_sent(span, valid=False)
        return f"Error fetching inventory: {e}"


@tool
def get_product_stock_direct(product_id: int) -> str:
    """
    Fetches the stock level for a specific product by its integer ID.
    """
    rl, mode = _get_ctx()
    span = rl.mark_tool_request_sent("get_product_stock_direct") if rl else None
    url = f"http://localhost:8000/{mode}/stock/{product_id}"
    try:
        if span:
            rl.mark_tool_request_received(span)
        response = requests.get(url, timeout=5)
        data = response.json()
        if span:
            rl.mark_tool_response_sent(span, status_code=response.status_code,
                                       valid=response.status_code in (200, 201))
        return str(data)
    except Exception as e:
        if span:
            rl.mark_tool_response_sent(span, valid=False)
        return f"Error fetching stock: {e}"


@tool
def place_order_direct(customer_id: int, product_id: int, quantity: int) -> str:
    """
    Places an order for a customer. Requires customer_id, product_id, and quantity.
    """
    rl, mode = _get_ctx()
    span = rl.mark_tool_request_sent("place_order_direct") if rl else None
    url = f"http://localhost:8000/{mode}/orders"
    payload = {"customer_id": customer_id, "product_id": product_id, "quantity": quantity}
    try:
        if span:
            rl.mark_tool_request_received(span)
        response = requests.post(url, json=payload, timeout=5)
        data = response.json()
        if span:
            rl.mark_tool_response_sent(span, status_code=response.status_code,
                                       valid=response.status_code in (200, 201))
        return str(data)
    except Exception as e:
        if span:
            rl.mark_tool_response_sent(span, valid=False)
        return f"Error placing order: {e}"


@tool
def get_customer_direct(customer_id: int) -> str:
    """
    Fetches customer information (name, email, tier) by customer ID.
    """
    rl, mode = _get_ctx()
    span = rl.mark_tool_request_sent("get_customer_direct") if rl else None
    url = f"http://localhost:8000/{mode}/customers/{customer_id}"
    try:
        if span:
            rl.mark_tool_request_received(span)
        response = requests.get(url, timeout=5)
        data = response.json()
        if span:
            rl.mark_tool_response_sent(span, status_code=response.status_code,
                                       valid=response.status_code in (200, 201))
        return str(data)
    except Exception as e:
        if span:
            rl.mark_tool_response_sent(span, valid=False)
        return f"Error fetching customer: {e}"


@tool
def get_discounts_direct(product_id: int) -> str:
    """
    Looks up the discount rate for a product.
    Returns a discount rate between 0.0 (no discount) and 1.0 (100% off).
    """
    rl, mode = _get_ctx()
    span = rl.mark_tool_request_sent("get_discounts_direct") if rl else None
    url = f"http://localhost:8000/{mode}/discounts"
    try:
        if span:
            rl.mark_tool_request_received(span)
        response = requests.get(url, params={"product_id": product_id}, timeout=5)
        data = response.json()
        if span:
            rl.mark_tool_response_sent(span, status_code=response.status_code,
                                       valid=response.status_code in (200, 201))
        return str(data)
    except Exception as e:
        if span:
            rl.mark_tool_response_sent(span, valid=False)
        return f"Error fetching discount: {e}"


# ---------------------------------------------------------------------------
# Approach wrapper
# ---------------------------------------------------------------------------

class DirectCallingApproach:
    """Encapsulates the direct-calling tools for the benchmark runner."""

    def __init__(self, scenario: str):
        self.scenario = scenario
        self.tools = [
            get_inventory_direct,
            get_product_stock_direct,
            place_order_direct,
            get_customer_direct,
            get_discounts_direct,
        ]

    def set_context(self, run_log: RunLogger, mode: str, iteration: int):
        """
        Inject per-iteration metadata into context variables.
        ContextVar is compatible with the thread pooling used by LangGraph.
        """
        _run_log_var.set(run_log)
        _mode_var.set(mode)
