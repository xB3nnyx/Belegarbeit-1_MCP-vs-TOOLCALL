from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional, Any, Dict
import random
import time

app = FastAPI(title="Benchmark Mock API")

# ---------------------------------------------------------------------------
# Mock-Daten
# ---------------------------------------------------------------------------

INVENTORY = [
    {"id": 1, "name": "Laptop",      "price": 999.99, "stock": 10},
    {"id": 2, "name": "Smartphone",  "price": 599.50, "stock": 25},
    {"id": 3, "name": "Tablet",      "price": 299.00, "stock": 15},
    {"id": 4, "name": "Headphones",  "price": 149.00, "stock": 40},
    {"id": 5, "name": "Smartwatch",  "price": 249.00, "stock": 8},
    {"id": 6, "name": "VR Headset",  "price": 444.99, "stock": 0},
]

CUSTOMERS = [
    {"id": 1, "name": "Alice Müller",  "email": "alice@example.com",  "tier": "gold"},
    {"id": 2, "name": "Bob Schmidt",   "email": "bob@example.com",    "tier": "silver"},
    {"id": 3, "name": "Clara Braun",   "email": "clara@example.com",  "tier": "bronze"},
]

ORDERS: List[Dict] = []  # in-memory storage
_order_counter = 100

DISCOUNTS = {
    1: 0.10,  # 10 % on Laptops
    2: 0.05,  # 5 % on Smartphones
    4: 0.15,  # 15 % on Headphones
}


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------

class Product(BaseModel):
    id: int
    name: str
    price: float
    stock: int

class Customer(BaseModel):
    id: int
    name: str
    email: str
    tier: str

class OrderRequest(BaseModel):
    customer_id: int
    product_id: int
    quantity: int

class Order(BaseModel):
    order_id: int
    customer_id: int
    product_id: int
    quantity: int
    total_price: float
    status: str


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
def health_check():
    return {"status": "healthy"}


# ===========================================================================
# SUNNY ENDPOINTS  -  clean schemas, predictable responses
# ===========================================================================

@app.get("/sunny/products", response_model=List[Product])
def get_products_sunny():
    """Returns a list of all products with clean types and full descriptions."""
    return INVENTORY


@app.get("/sunny/stock/{product_id}")
def get_stock_sunny(product_id: int):
    """Returns the current stock level for a specific product (clean)."""
    for item in INVENTORY:
        if item["id"] == product_id:
            return {"product_id": product_id, "stock": item["stock"]}
    raise HTTPException(status_code=404, detail="Product not found")


@app.post("/sunny/orders", response_model=Order, status_code=201)
def place_order_sunny(order: OrderRequest):
    """Places an order for the given customer and product. Returns the created order."""
    global _order_counter
    product = next((p for p in INVENTORY if p["id"] == order.product_id), None)
    customer = next((c for c in CUSTOMERS if c["id"] == order.customer_id), None)

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    if product["stock"] < order.quantity:
        raise HTTPException(status_code=409, detail="Insufficient stock")

    # NOTE: Stock is NOT deducted — this is a mock API used for benchmarking.
    # Deducting stock would cause 409 failures after N iterations (stock runs out).
    _order_counter += 1
    new_order = {
        "order_id":    _order_counter,
        "customer_id": order.customer_id,
        "product_id":  order.product_id,
        "quantity":    order.quantity,
        "total_price": round(product["price"] * order.quantity, 2),
        "status":      "confirmed",
    }
    ORDERS.append(new_order)
    return new_order


@app.get("/sunny/customers/{customer_id}", response_model=Customer)
def get_customer_sunny(customer_id: int):
    """Returns customer information by ID (clean)."""
    customer = next((c for c in CUSTOMERS if c["id"] == customer_id), None)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer


@app.get("/sunny/discounts")
def get_discounts_sunny(product_id: int = Query(..., description="Product ID to look up discount for")):
    """Returns the discount rate (0.0-1.0) for a given product. Returns 0.0 if no discount exists."""
    discount = DISCOUNTS.get(product_id, 0.0)
    return {"product_id": product_id, "discount_rate": discount}


# ===========================================================================
# DIRTY ENDPOINTS  -  inconsistent schemas, random errors, vague descriptions
# ===========================================================================

@app.get("/dirty/products")
def get_products_dirty():
    """
    Gets stuff. May or may not return complete data.
    """
    # Status Code Lying: ~5% chance — return HTTP 500 but put valid data in the body
    if random.random() < 0.05:
        valid_data = [{"id": i["id"], "name": i["name"], "price": i["price"], "stock": i["stock"]} for i in INVENTORY]
        raise HTTPException(status_code=500, detail={"_lie": True, "message": "DB flush error (transient)", "data": valid_data})

    # Status Code Lying: ~5% chance — return HTTP 200 but with an error envelope
    if random.random() < 0.05:
        return {"error": "Upstream cache miss", "code": 503, "retryable": True}

    if random.random() < 0.15:
        raise HTTPException(status_code=500, detail="Internal Server Error (Simulated)")

    # Schema Chaos: ~5% chance — completely rename all keys
    if random.random() < 0.05:
        chaos_data = []
        for item in INVENTORY:
            chaos_data.append({
                "pid":          item["id"],
                "p_name":       item["name"],
                "price":        {"val": item["price"], "cur": "EUR"},
                "inventory_qty": item["stock"],
            })
        return chaos_data

    dirty_data = []
    for item in INVENTORY:
        d = item.copy()
        choice = random.choice(["string_price", "missing_stock", "extra_fields", "normal"])
        if choice == "string_price":
            d["price"] = f"{item['price']} EUR"
        elif choice == "missing_stock":
            del d["stock"]
        elif choice == "extra_fields":
            d["metadata"] = {"info": "vague", "quality": "unknown"}
        dirty_data.append(d)
    return dirty_data


@app.get("/dirty/stock/{pid}")
def get_stock_dirty(pid: str):
    """
    Checks stock. pid should be a number probably.
    """
    try:
        int_id = int(pid)
    except ValueError:
        return {"error": "invalid format, maybe?"}

    for item in INVENTORY:
        if item["id"] == int_id:
            # Status Code Lying: ~5% — return HTTP 200 with an error body (no real data)
            if random.random() < 0.05:
                return {"error": "Lock contention on row", "code": 500, "product_id": int_id}

            # Schema Chaos: ~5% — deeply nested structure
            if random.random() < 0.05:
                return {"product": {"ref": int_id, "availability": {"units": item["stock"], "status": "ok"}}}

            # Standard dirty: sometimes a list, sometimes unexpected key
            if random.random() < 0.5:
                return [item["stock"]]
            return {"stock_level": item["stock"]}
    return {"msg": "nothing found"}


@app.post("/dirty/orders")
def place_order_dirty(payload: Dict[str, Any]):
    """
    Creates order maybe. Fields are loosely validated.
    """
    global _order_counter
    if random.random() < 0.15:
        raise HTTPException(status_code=500, detail="Oops")

    # Accept both 'product_id' and 'pid' for robustness testing
    product_id = payload.get("product_id") or payload.get("pid")
    customer_id = payload.get("customer_id") or payload.get("cid")
    quantity = payload.get("quantity", 1)

    try:
        product_id = int(product_id)
        customer_id = int(customer_id)
        quantity = int(quantity)
    except (TypeError, ValueError):
        return {"err": "bad input"}

    product = next((p for p in INVENTORY if p["id"] == product_id), None)
    if not product:
        return {"err": "unknown product"}

    _order_counter += 1
    total = round(product["price"] * quantity, 2)

    # Status Code Lying: ~5% — HTTP 200 but error body (no order was placed)
    if random.random() < 0.05:
        return {"error": "Order queue full", "code": 503, "order_id": None}

    # Schema Chaos: ~5% — deeply nested, non-standard keys
    if random.random() < 0.05:
        return {
            "transaction": {
                "ref": _order_counter,
                "amount": {"value": total, "currency": "EUR"},
                "outcome": "pending_confirmation",
            }
        }

    # Standard dirty: vary response shape
    if random.random() < 0.5:
        return {"id": _order_counter, "total": total, "ok": True}
    return {"order_id": _order_counter, "total_price": f"{total} EUR", "status": "maybe confirmed"}


@app.get("/dirty/customers/{cid}")
def get_customer_dirty(cid: str):
    """
    Fetches user data. cid is a string for some reason.
    """
    try:
        int_id = int(cid)
    except ValueError:
        return {"error": "bad id"}

    customer = next((c for c in CUSTOMERS if c["id"] == int_id), None)
    if not customer:
        return {"msg": "not found or something"}

    # Status Code Lying: ~5% — HTTP 200 but error body
    if random.random() < 0.05:
        return {"error": "Customer record locked", "code": 423, "id": int_id}

    # Schema Chaos: ~5% — deeply nested, non-standard keys
    if random.random() < 0.05:
        return {
            "user": {
                "uid": customer["id"],
                "display": customer["name"],
                "contact": {"mail": customer["email"]},
                "membership": customer["tier"],
            }
        }

    # Standard dirty: randomly rename or drop fields
    d = customer.copy()
    choice = random.choice(["rename_name", "drop_email", "add_noise", "normal"])
    if choice == "rename_name":
        d["customer_name"] = d.pop("name")
    elif choice == "drop_email":
        del d["email"]
    elif choice == "add_noise":
        d["internal_ref"] = "XK-29-Z"
    return d


@app.get("/dirty/discounts")
def get_discounts_dirty(pid: str = Query(None), product_id: str = Query(None)):
    """
    Returns discount. Maybe. Use pid or product_id, doesn't matter.
    """
    raw_id = pid or product_id
    if raw_id is None:
        return {"error": "need some kind of id"}
    try:
        int_id = int(raw_id)
    except ValueError:
        return {"discount": None, "reason": "bad id format"}

    discount = DISCOUNTS.get(int_id)
    if discount is None:
        return {"discount": "none"}  # string instead of null

    # Status Code Lying: ~5% — HTTP 200 but error body (no discount value)
    if random.random() < 0.05:
        return {"error": "Discount engine timeout", "code": 504, "product_id": int_id}

    # Schema Chaos: ~5% — non-standard nested structure
    if random.random() < 0.05:
        return {"promotion": {"item_ref": int_id, "reduction": {"pct": int(discount * 100), "absolute": round(discount, 4)}}}

    # Randomly return as percentage string or float
    if random.random() < 0.5:
        return {"rate": f"{int(discount * 100)}%"}
    return {"discount_rate": discount, "product": int_id}

