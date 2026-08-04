import csv
import os

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "products.csv")
FIELDNAMES = ["product_id", "name", "quantity", "unit", "alert_threshold"]


def read_products():
    """Load every row from products.csv into a list of dicts."""
    if not os.path.exists(CSV_PATH):
        return []
    with open(CSV_PATH, newline="") as f:
        reader = csv.DictReader(f)
        products = []
        for row in reader:
            row["product_id"] = int(row["product_id"])
            row["quantity"] = float(row["quantity"])
            row["alert_threshold"] = float(row["alert_threshold"])
            products.append(row)
        return products


@app.get("/inventory")
def get_inventory():
    """Return the full product list."""
    return read_products()


class ProductCreate(BaseModel):
    name: str
    quantity: float
    unit: str
    alert_threshold: float = 10


@app.post("/inventory", status_code=201)
def create_product(product: ProductCreate):
    """Register a new product."""
    if product.quantity < 0:
        raise HTTPException(status_code=400, detail="quantity cannot be negative")

    if product.unit.lower() == "units" and product.quantity != int(product.quantity):
        raise HTTPException(
            status_code=400,
            detail="quantity must be a whole number for unit 'units'",
        )

    products = read_products()
    new_product = {
        "product_id": get_next_id(products),
        "name": product.name,
        "quantity": product.quantity,
        "unit": product.unit,
        "alert_threshold": product.alert_threshold,
    }
    append_product(new_product)
    return new_product


class StockUpdate(BaseModel):
    delta: float


def write_products(products):
    """Overwrite products.csv with the given list of products, unchanged rows included."""
    with open(CSV_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(products)


@app.patch("/inventory/{product_id}")
def update_stock(product_id: int, update: StockUpdate):
    """Adjust a product's stock by a signed delta (positive = incoming, negative = outgoing)."""
    products = read_products()

    product = next((p for p in products if p["product_id"] == product_id), None)
    if product is None:
        raise HTTPException(status_code=404, detail="product not found")

    if product["unit"].lower() == "units" and update.delta != int(update.delta):
        raise HTTPException(
            status_code=400,
            detail="delta must be a whole number for unit 'units'",
        )

    new_quantity = product["quantity"] + update.delta
    if new_quantity < 0:
        raise HTTPException(
            status_code=400, detail="update would push quantity below zero"
        )

    product["quantity"] = new_quantity
    write_products(products)
    return product


@app.get("/inventory/alerts")
def get_alerts():
    """Return every product whose quantity is currently below its own alert_threshold."""
    products = read_products()
    return [p for p in products if p["quantity"] < p["alert_threshold"]]