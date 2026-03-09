"""
MCP Wrapper Server for the Benchmark.

Response format: all tools return a JSON string with a "_status" key (HTTP
status code) and a "result" key (the normalised payload). The runner strips
"_status" before forwarding the result to the LLM, so the agent always sees
clean data while the runner can log the real HTTP status code.

Example: '{"_status": 200, "result": [{"id": 1, ...}]}'
"""
import json
import os
import requests
from fastmcp import FastMCP

mcp = FastMCP("BenchmarkServer")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ok(data) -> str:
    """Wrap a successful result with status 200."""
    return json.dumps({"_status": 200, "result": data})


def _err(status_code: int, message: str) -> str:
    """Wrap an error result with the given HTTP status code."""
    return json.dumps({"_status": status_code, "result": message})


def _parse_price(raw) -> float:
    if raw is None: return 0.0
    if isinstance(raw, (int, float)): return float(raw)
    try: return float(str(raw).split()[0])
    except ValueError: return 0.0


def _parse_discount(raw) -> float:
    if raw is None or raw == "none": return 0.0
    if isinstance(raw, (int, float)): return float(raw)
    s = str(raw).strip()
    if s.endswith("%"):
        try: return float(s[:-1]) / 100
        except ValueError: return 0.0
    try: return float(s)
    except ValueError: return 0.0


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def get_inventory_mcp(mode: str = "sunny") -> str:
    """
    Fetches the current product inventory from the API.
    Returns a list of products with id, name, price and stock.
    """
    url = f"http://localhost:8000/{mode}/products"
    try:
        response = requests.get(url, timeout=5)
        data = response.json()
        if not response.ok:
            # Status Code Lying (500 with valid data in detail.data)
            if isinstance(data, dict) and "detail" in data:
                detail = data["detail"]
                if isinstance(detail, dict) and detail.get("_lie") and "data" in detail:
                    return _ok(detail["data"])
            return _err(response.status_code, str(data))
        # Lying-200: HTTP 200 but body contains error envelope
        if isinstance(data, dict) and "error" in data:
            return _err(data.get("code", 503), data["error"])
        return _ok(data)
    except requests.HTTPError as e:
        return _err(e.response.status_code, f"HTTP Error: {e}")
    except Exception as e:
        return _err(-1, f"MCP Error: {e}")


@mcp.tool()
def get_stock_mcp(product_id: int, mode: str = "sunny") -> str:
    """
    Fetches the stock level for a specific product by its integer ID.
    Normalises the response so the agent always receives a consistent dict.
    """
    url = f"http://localhost:8000/{mode}/stock/{product_id}"
    try:
        response = requests.get(url, timeout=5)
        data = response.json()
        if not response.ok:
            return _err(response.status_code, str(data))
        # Lying-200: HTTP 200 but body is an error envelope
        if isinstance(data, dict) and "error" in data:
            return _err(data.get("code", 500), data["error"])
        # Standard dirty: list response → normalise to dict
        elif isinstance(data, list) and data:
            data = {"stock": data[0]}
        return _ok(data)
    except requests.HTTPError as e:
        return _err(e.response.status_code, f"HTTP Error: {e}")
    except Exception as e:
        return _err(-1, f"MCP Error: {e}")


@mcp.tool()
def place_order_mcp(customer_id: int, product_id: int, quantity: int, mode: str = "sunny") -> str:
    """
    Places an order for a customer.
    Always returns a normalised dict with keys: order_id, total_price (float), status.
    """
    url = f"http://localhost:8000/{mode}/orders"
    payload = {"customer_id": customer_id, "product_id": product_id, "quantity": quantity}
    try:
        response = requests.post(url, json=payload, timeout=5)
        data = response.json()
        # Lying-200: HTTP 200 but body is an error envelope (no order was placed)
        if response.ok and isinstance(data, dict) and "error" in data:
            return _err(data.get("code", 503), data["error"])
        # Standard dirty: nested transaction structure
        data = {
            "order_id":    data.get("order_id") or data.get("id"),
            "total_price": _parse_price(data.get("total_price") or data.get("total")),
            "status":      data.get("status", "unknown"),
        }
        return _ok(data) if response.ok else _err(response.status_code, str(data))
    except requests.HTTPError as e:
        return _err(e.response.status_code, f"HTTP Error: {e}")
    except Exception as e:
        return _err(-1, f"MCP Error placing order: {e}")


@mcp.tool()
def get_customer_mcp(customer_id: int, mode: str = "sunny") -> str:
    """
    Fetches customer information by ID.
    Always returns a normalised dict with keys: id, name, email, tier.
    """
    url = f"http://localhost:8000/{mode}/customers/{customer_id}"
    try:
        response = requests.get(url, timeout=5)
        data = response.json()
        # Lying-200: HTTP 200 but body is an error envelope
        if response.ok and isinstance(data, dict) and "error" in data:
            return _err(data.get("code", 500), data["error"])

        normalized = {
            "id":    data.get("id"),
            "name":  data.get("name") or data.get("customer_name", "unknown"),
            "email": data.get("email", "unknown"),
            "tier":  data.get("tier", "unknown"),
        }
        return _ok(normalized)
    except requests.HTTPError as e:
        return _err(e.response.status_code, f"HTTP Error: {e}")
    except Exception as e:
        return _err(-1, f"MCP Error fetching customer: {e}")


@mcp.tool()
def get_discounts_mcp(product_id: int, mode: str = "sunny") -> str:
    """
    Looks up the discount rate for a product.
    Always returns a normalised dict with keys: product_id, discount_rate (float, 0.0-1.0).
    """
    url = f"http://localhost:8000/{mode}/discounts"
    try:
        response = requests.get(url, params={"product_id": product_id}, timeout=5)
        data = response.json()
        # Lying-200: HTTP 200 but body is an error envelope
        if response.ok and isinstance(data, dict) and "error" in data:
            return _err(data.get("code", 504), data["error"])

        raw = data.get("discount_rate") or data.get("rate") or data.get("discount")
        normalized = {
            "product_id":    product_id,
            "discount_rate": _parse_discount(raw),
        }
        return _ok(normalized)
    except requests.HTTPError as e:
        return _err(e.response.status_code, f"HTTP Error: {e}")
    except Exception as e:
        return _err(-1, f"MCP Error fetching discount: {e}")


if __name__ == "__main__":
    mcp.run()
