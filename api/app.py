import csv
import os

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "products.csv")
FIELDNAMES = ["product_id", "name", "quantity", "unit", "alert_threshold"]

def ensure_csv_exists():
    """Create products.csv with a header row if it's missing, or repair it
    if the file exists but doesn't start with a valid header."""
    has_valid_header = False
    if os.path.exists(CSV_PATH):
        with open(CSV_PATH, newline="") as f:
            first_line = f.readline().strip()
        has_valid_header = first_line == ",".join(FIELDNAMES)

    if not has_valid_header:
        with open(CSV_PATH, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()

ensure_csv_exists()

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


def get_next_id(products):
    """Next auto-incrementing product_id: 1 if the file is empty, otherwise max + 1."""
    if not products:
        return 1
    return max(p["product_id"] for p in products) + 1


def append_product(product):
    """Add one new row to products.csv without touching the existing rows."""
    with open(CSV_PATH, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writerow(product)
        

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


class ThresholdUpdate(BaseModel):
    alert_threshold: float


@app.patch("/inventory/{product_id}/threshold")
def update_threshold(product_id: int, update: ThresholdUpdate):
    """Change the low-stock alert threshold for an existing product."""
    products = read_products()

    product = next((p for p in products if p["product_id"] == product_id), None)
    if product is None:
        raise HTTPException(status_code=404, detail="product not found")

    if update.alert_threshold < 0:
        raise HTTPException(status_code=400, detail="alert_threshold cannot be negative")

    if product["unit"].lower() == "units" and update.alert_threshold != int(update.alert_threshold):
        raise HTTPException(
            status_code=400,
            detail="alert_threshold must be a whole number for unit 'units'",
        )

    product["alert_threshold"] = update.alert_threshold
    write_products(products)
    return product