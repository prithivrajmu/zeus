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


def test_brand1_aa_deterministic_and_brand_stamped():
    a = get("brand1_aa")(GeneratorConfig(count=200, seed=42)).generate_tables()
    b = get("brand1_aa")(GeneratorConfig(count=200, seed=42)).generate_tables()
    assert a == b  # deterministic under a fixed seed
    # every fact-shaped table stamps brand_id = 1 (masters carry ref data:
    # raw_product_master brand_id is null for competitor products by design)
    fact_tables = {
        "raw_epi", "raw_elaad_claims", "raw_elaad_persistency", "raw_finance",
        "raw_npa", "raw_spp_hub", "raw_pld_switching", "raw_pld_projected",
        "raw_hcp_atu", "raw_xponent", "raw_brand_master", "raw_geo_alignment",
    }
    for name in fact_tables:
        assert all(r.get("brand_id") == 1 for r in a[name]), name


def test_brand1_aa_referential_integrity():
    t = get("brand1_aa")(GeneratorConfig(count=200, seed=42)).generate_tables()
    align_ids = {a["align_id"] for a in t["raw_geo_alignment"]}
    assert align_ids  # non-empty
    assert all(c["align_id"] in align_ids for c in t["raw_elaad_claims"])
    assert all(h["align_id"] in align_ids for h in t["raw_xponent"])
    assert all(b["align_id"] in align_ids for b in t["raw_geo_alignment_bridge"])


def test_brand1_aa_funnel_reconciles_to_anchors():
    t = get("brand1_aa")(GeneratorConfig(count=50, seed=1)).generate_tables()
    epi = {r["scenario"]: r for r in t["raw_epi"]}
    # OP26 budget Brand1-written should match the PDF-derived 22,683 (±1)
    assert abs(epi["OP26 Budget"]["brand1_written"] - 22_683) <= 1
    # Atlanta district anchored exactly (journey health ≈ 4.3%)
    atl = [a for a in t["raw_geo_alignment"] if a["align_name"] == "DERM ABM Atlanta"][0]
    claims = [c for c in t["raw_elaad_claims"] if c["align_id"] == atl["align_id"]]
    diag = sum(c["aa_diagnosed_pts"] for c in claims)
    brand = sum(c["brand_treated_pts"] for c in claims)
    assert round(brand / diag, 3) == 0.043


def test_brand1_aa_clean_option():
    t = get("brand1_aa")(GeneratorConfig(count=50, seed=1, options={"clean": "true"})).generate_tables()
    assert all(s["paid_fills_90d"] >= 0 for s in t["raw_spp_hub"])
