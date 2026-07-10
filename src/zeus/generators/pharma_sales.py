"""Use case 2: pharma brand sales across countries.

Emits RAW source tables for an ETL/ELT pipeline that will build marts such
as brand_performance_by_market, distributor_scorecard, fx_normalized_sales:

    raw_products        brand portfolio: molecule, therapeutic area, launch year
    raw_countries       markets: region, currency, price index, regulated flag
    raw_distributors    channel partners per country
    raw_fx_rates        monthly currency → USD rates (for FX normalization in ETL)
    raw_sales           monthly sell-in transactions in LOCAL currency:
                        brand x country x distributor x month, units + value

`--count` controls the number of monthly sales transactions.
Sales values are intentionally in local currency with only an fx table to
join on — normalizing to USD is the pipeline's job, not the generator's.

Realism knobs: seasonality (respiratory brands peak in winter), brand launch
dates (no sales before launch), loss-of-exclusivity decay, and ~1% messy
rows (trailing spaces in country codes, occasional negative unit returns)
unless -o clean=true.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Any

from zeus.core import BaseGenerator, register

# (brand, molecule, therapeutic_area, launch_year, base_unit_price_usd, seasonal)
PRODUCTS = [
    ("Cardivex", "amlodipril", "Cardiovascular", 2015, 4.20, False),
    ("Glucora", "sitaformin", "Diabetes", 2017, 6.80, False),
    ("Respilar", "flutinide", "Respiratory", 2016, 9.50, True),
    ("Neurantis", "gabapentra", "CNS", 2019, 12.40, False),
    ("Oncovia", "pembrizumab", "Oncology", 2021, 480.00, False),
    ("Dermaquil", "tacrolim", "Dermatology", 2014, 7.10, False),
    ("Immunara", "adalizumab", "Immunology", 2018, 310.00, False),
    ("Gastrelle", "esomezole", "Gastroenterology", 2012, 3.30, False),
    ("Febrinox", "ibucetamol", "Pain & Fever", 2010, 1.10, True),
    ("Vaxigen-Q", "quadrivalent flu antigen", "Vaccines", 2013, 14.00, True),
]

# (iso2, country, region, currency, approx units per USD, price_index, regulated_pricing)
COUNTRIES = [
    ("US", "United States", "North America", "USD", 1.0, 1.00, False),
    ("DE", "Germany", "Europe", "EUR", 0.92, 0.72, True),
    ("FR", "France", "Europe", "EUR", 0.92, 0.68, True),
    ("GB", "United Kingdom", "Europe", "GBP", 0.79, 0.70, True),
    ("JP", "Japan", "Asia Pacific", "JPY", 149.0, 0.65, True),
    ("CN", "China", "Asia Pacific", "CNY", 7.2, 0.45, True),
    ("IN", "India", "Asia Pacific", "INR", 83.5, 0.18, True),
    ("BR", "Brazil", "Latin America", "BRL", 5.4, 0.38, True),
    ("MX", "Mexico", "Latin America", "MXN", 17.8, 0.35, False),
    ("CA", "Canada", "North America", "CAD", 1.36, 0.75, True),
    ("AU", "Australia", "Asia Pacific", "AUD", 1.52, 0.72, True),
    ("ZA", "South Africa", "Middle East & Africa", "ZAR", 18.6, 0.30, False),
]

CHANNELS = ["wholesaler", "hospital_direct", "pharmacy_chain", "government_tender"]


@register
class PharmaSales(BaseGenerator):
    name = "pharma_sales"
    description = "Pharma raw tables: products, countries, distributors, FX rates, monthly sales in local currency."

    def generate_tables(self) -> dict[str, list[dict[str, Any]]]:
        n_sales = self.config.count
        months_back = int(self.opt("months", 36))
        messy = str(self.opt("clean", "false")).lower() != "true"

        products = self._products()
        countries = self._countries()
        distributors = self._distributors(countries)
        fx_rates, month_list = self._fx_rates(countries, months_back)
        sales = self._sales(n_sales, products, countries, distributors, month_list, messy)

        return {
            "raw_products": products,
            "raw_countries": countries,
            "raw_distributors": distributors,
            "raw_fx_rates": fx_rates,
            "raw_sales": sales,
        }

    def _products(self) -> list[dict[str, Any]]:
        return [
            {
                "product_id": f"PRD-{i+1:03d}",
                "brand_name": b,
                "molecule": mol,
                "therapeutic_area": ta,
                "launch_year": launch,
                "patent_expiry_year": launch + 12,
                "base_unit_price_usd": price,
            }
            for i, (b, mol, ta, launch, price, _) in enumerate(PRODUCTS)
        ]

    def _countries(self) -> list[dict[str, Any]]:
        return [
            {
                "country_code": iso,
                "country_name": name,
                "region": region,
                "currency_code": ccy,
                "price_index": idx,
                "regulated_pricing": reg,
            }
            for iso, name, region, ccy, _, idx, reg in COUNTRIES
        ]

    def _distributors(self, countries) -> list[dict[str, Any]]:
        rows = []
        did = 0
        for c in countries:
            for _ in range(self.rng.randint(2, 4)):
                did += 1
                rows.append({
                    "distributor_id": f"DST-{did:04d}",
                    "distributor_name": f"{self.faker.last_name()} {self.rng.choice(['Pharma', 'MedSupply', 'Healthcare', 'Distribution'])}",
                    "country_code": c["country_code"],
                    "channel": self.rng.choice(CHANNELS),
                    "active_since": self.faker.date_between("-10y", "-1y").isoformat(),
                    "credit_rating": self.rng.choice(["AAA", "AA", "A", "BBB", "BB"]),
                })
        return rows

    def _fx_rates(self, countries, months_back) -> tuple[list, list]:
        today = date.today().replace(day=1)
        months = []
        y, m = today.year, today.month
        for _ in range(months_back):
            months.append(f"{y:04d}-{m:02d}")
            m -= 1
            if m == 0:
                y, m = y - 1, 12
        months.reverse()

        base = {iso: rate for iso, *_ in [(c[0],) for c in COUNTRIES] for _ in ()}  # placeholder
        base = {c[0]: c[4] for c in COUNTRIES}
        rows = []
        for iso, _, _, ccy, rate, _, _ in COUNTRIES:
            drift = rate
            for month in months:
                drift *= self.rng.uniform(0.985, 1.015)  # gentle random walk
                rows.append({
                    "month": month,
                    "currency_code": ccy,
                    "usd_per_unit": round(1.0 / drift, 6),
                    "units_per_usd": round(drift, 4),
                })
        # de-dupe EUR (DE/FR share it) keeping first occurrence per month
        seen = set()
        deduped = []
        for r in rows:
            key = (r["month"], r["currency_code"])
            if key not in seen:
                seen.add(key)
                deduped.append(r)
        return deduped, months

    def _sales(self, n, products, countries, distributors, months, messy) -> list[dict[str, Any]]:
        dist_by_country = {}
        for d in distributors:
            dist_by_country.setdefault(d["country_code"], []).append(d)
        seasonal = {b: s for b, _, _, _, _, s in PRODUCTS}
        fx = {c[0]: c[4] for c in COUNTRIES}
        this_year = date.today().year

        rows = []
        for i in range(n):
            p = self.rng.choice(products)
            c = self.rng.choice(countries)
            month = self.rng.choice(months)
            year, mon = int(month[:4]), int(month[5:7])

            if year < p["launch_year"]:
                month = f"{p['launch_year']:04d}-{mon:02d}"
                year = p["launch_year"]

            units = int(self.rng.lognormvariate(7.5, 1.0))
            if seasonal[p["brand_name"]]:
                units = int(units * (1 + 0.6 * math.cos((mon - 1) / 12 * 2 * math.pi)))  # winter peak
            if year > p["patent_expiry_year"]:
                units = int(units * 0.45)  # loss of exclusivity

            local_price = p["base_unit_price_usd"] * c["price_index"] * fx[c["country_code"]]
            local_price *= self.rng.uniform(0.92, 1.08)
            gross = round(units * local_price, 2)
            rebate = round(gross * (self.rng.uniform(0.15, 0.35) if c["regulated_pricing"] else self.rng.uniform(0.05, 0.15)), 2)

            country_code = c["country_code"]
            if messy and self.rng.random() < 0.008:
                country_code = country_code + " "  # trailing space for ETL to trim
            if messy and self.rng.random() < 0.004:
                units = -abs(int(units * 0.1))  # product return
                gross = round(units * local_price, 2)
                rebate = 0.0

            rows.append({
                "sale_id": f"SAL-{i+1:08d}",
                "month": month,
                "product_id": p["product_id"],
                "brand_name": p["brand_name"],
                "country_code": country_code,
                "distributor_id": self.rng.choice(dist_by_country[c["country_code"]])["distributor_id"],
                "currency_code": c["currency_code"],
                "units_sold": units,
                "gross_sales_local": gross,
                "rebates_local": rebate,
                "net_sales_local": round(gross - rebate, 2),
            })
        return rows
