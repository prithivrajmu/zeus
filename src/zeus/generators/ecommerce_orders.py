"""Use case 2: e-commerce orders.

Orders with line items, consistent totals (subtotal + tax + shipping −
discount = total), payment/fulfillment status, and repeat customers.
"""

from __future__ import annotations

from typing import Any, Iterator

from zeus.core import BaseGenerator, register

CATALOG = [
    ("Wireless Mouse", "electronics", 24.99),
    ("Mechanical Keyboard", "electronics", 89.99),
    ("USB-C Hub", "electronics", 39.99),
    ("Noise-Cancelling Headphones", "electronics", 199.99),
    ("Laptop Stand", "office", 51.25),
    ("Ergonomic Chair", "office", 349.00),
    ("Desk Lamp", "office", 32.50),
    ("Notebook 3-Pack", "office", 12.99),
    ("Stainless Water Bottle", "lifestyle", 21.00),
    ("Yoga Mat", "lifestyle", 28.75),
    ("Running Shoes", "lifestyle", 119.99),
    ("Backpack 25L", "lifestyle", 64.99),
    ("Espresso Grinder", "kitchen", 149.00),
    ("Chef's Knife 8in", "kitchen", 79.99),
    ("Cast Iron Skillet", "kitchen", 44.95),
]

PAYMENT_STATUS = ["paid", "paid", "paid", "paid", "refunded", "failed", "pending"]
FULFILLMENT = ["delivered", "delivered", "shipped", "processing", "cancelled", "returned"]
PAYMENT_METHODS = ["credit_card", "debit_card", "paypal", "apple_pay", "gift_card"]


@register
class EcommerceOrders(BaseGenerator):
    name = "ecommerce_orders"
    description = "E-commerce orders with line items, consistent totals, and fulfillment status."

    def generate(self) -> Iterator[dict[str, Any]]:
        # Pool of repeat customers so joins/aggregations are interesting.
        n_customers = int(self.opt("customers", max(10, self.config.count // 4)))
        customers = [
            {
                "id": f"CUST-{i+1:05d}",
                "name": self.faker.name(),
                "email": self.faker.email(),
                "city": self.faker.city(),
                "country": self.faker.country_code(),
            }
            for i in range(n_customers)
        ]

        for i in range(self.config.count):
            cust = self.rng.choice(customers)
            n_items = self.rng.choices([1, 2, 3, 4], weights=[45, 30, 17, 8])[0]
            items = []
            subtotal = 0.0
            for name, cat, price in self.rng.sample(CATALOG, n_items):
                qty = self.rng.choices([1, 2, 3], weights=[75, 20, 5])[0]
                items.append({"product": name, "category": cat, "unit_price": price, "quantity": qty})
                subtotal += price * qty

            discount = round(subtotal * self.rng.choice([0, 0, 0, 0.05, 0.10, 0.15]), 2)
            tax = round((subtotal - discount) * 0.08, 2)
            shipping = 0.0 if subtotal >= 75 else 5.99
            total = round(subtotal - discount + tax + shipping, 2)

            yield {
                "order_id": f"ORD-{i+1:07d}",
                "customer_id": cust["id"],
                "customer_name": cust["name"],
                "customer_email": cust["email"],
                "ship_city": cust["city"],
                "ship_country": cust["country"],
                "order_date": self.faker.date_time_between("-365d", "now").isoformat(),
                "items": items,
                "item_count": sum(it["quantity"] for it in items),
                "subtotal": round(subtotal, 2),
                "discount": discount,
                "tax": tax,
                "shipping": shipping,
                "total": total,
                "payment_method": self.rng.choice(PAYMENT_METHODS),
                "payment_status": self.rng.choice(PAYMENT_STATUS),
                "fulfillment_status": self.rng.choice(FULFILLMENT),
            }
