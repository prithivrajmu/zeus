import zeus.generators  # noqa: F401  — triggers registration
from zeus.core import GeneratorConfig, get


def test_deterministic_with_seed():
    cfg = GeneratorConfig(count=10, seed=7)
    a = list(get("example_users")(cfg).generate())
    b = list(get("example_users")(GeneratorConfig(count=10, seed=7)).generate())
    assert a == b
    assert len(a) == 10


def test_options_passthrough():
    cfg = GeneratorConfig(count=1, seed=1, options={"domain": "acme.io"})
    rec = next(get("example_users")(cfg).generate())
    assert rec["email"].endswith("@acme.io")


def test_patient_history_referential_integrity():
    cfg = GeneratorConfig(count=50, seed=3)
    t = get("patient_history")(cfg).generate_tables()
    member_ids = {m["member_id"] for m in t["raw_members"]}
    claim_ids = {c["claim_id"] for c in t["raw_claims"]}
    assert all(c["member_id"] in member_ids for c in t["raw_claims"])
    assert all(l["claim_id"] in claim_ids for l in t["raw_claim_lines"])
    assert all(r["member_id"] in member_ids for r in t["raw_prescriptions"])
    assert "_chronic_codes" not in t["raw_members"][0]


def test_pharma_sales_no_pre_launch_and_fx_coverage():
    cfg = GeneratorConfig(count=2000, seed=3)
    t = get("pharma_sales")(cfg).generate_tables()
    launch = {p["product_id"]: p["launch_year"] for p in t["raw_products"]}
    assert all(int(s["month"][:4]) >= launch[s["product_id"]] for s in t["raw_sales"])
    fx_keys = {(f["month"], f["currency_code"]) for f in t["raw_fx_rates"]}
    assert all((s["month"], s["currency_code"]) in fx_keys for s in t["raw_sales"])


def test_clean_option_disables_messy_rows():
    cfg = GeneratorConfig(count=1000, seed=3, options={"clean": "true"})
    t = get("pharma_sales")(cfg).generate_tables()
    assert all(s["country_code"] == s["country_code"].strip() for s in t["raw_sales"])
    assert all(s["units_sold"] >= 0 for s in t["raw_sales"])
