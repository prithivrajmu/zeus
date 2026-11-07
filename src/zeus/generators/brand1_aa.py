"""Use case 3: Brand1 (Alopecia Areata) commercial analytics — the ARGOS dashboard.

Emits RAW source tables for the odysseus ELT pipeline, which builds the ARGOS
marts (exec KPI, patient funnel, market dynamics, subnational opportunity).
Every fact-shaped table carries ``brand_id`` so the same pipeline ingests the
whole 7-brand portfolio; this generator produces brand #1 (Brand1, brand_id=1).

Tables emitted
--------------
Masters (reference):
    raw_brand_master        the owned brand(s) this feed covers
    raw_product_master      Brand1 + JAK/systemic/topical competitors + class map
    raw_geo_master          universal base geography (National→…→ZIP3)
    raw_geo_alignment       the brand's sales alignment (DERM ABM) + base-geo map
Facts (all carry brand_id):
    raw_epi                 annual funnel anchors (Pts Seeking Tx, conversion %) — budget + actual
    raw_finance             monthly gross/net sales, GtN, revenue (+ scenario)
    raw_npa                 weekly + monthly Rx (TRx/NRx/NBRx/NWRx), factored + non-factored
    raw_elaad_claims        monthly patient claims per alignment node (diagnosed/treated/jak/brand + DOT)
    raw_elaad_persistency   cohort persistency curves
    raw_spp_hub             weekly fulfillment (fills, 90-day paid)
    raw_pld_switching       monthly from/to switching matrix centred on Brand1
    raw_pld_projected       monthly projected patients by treatment class
    raw_hcp_atu             quarterly ATU conversion rates (JAK / Brand1 written)
    raw_xponent             monthly HCP-level Rx

`--count` controls the number of HCPs (the volume driver for xponent / Rx).
Numbers are derived TOP-DOWN from the OP26 anchors below so tiles reconcile
(e.g. exec Net Sales ≈ funnel Net Revenue, funnel steps ≈ subnational rollup).
~1% messy rows (trailing spaces, negative returns) unless -o clean=true.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Any

from zeus.core import BaseGenerator, register

BRAND_ID = 1
BRAND_NAME = "Brand1"

# ---- National annual funnel anchors (from the ARGOS PDF) --------------------
# scenario -> (pts_seeking_tx, rx_written%, systemic%, jak%, brand1%,
#              fill_rate_90d, avg_annual_dot, gross_rev, gtn%, net_rev)
FUNNEL_ANCHORS = {
    "OP26 Budget": (625_000, 0.47, 0.27, 0.55, 0.52, 0.58, 7.32, 547_000_000, 0.60, 219_000_000),
    "YTD Actual":  (625_000, 0.44, 0.32, 0.53, 0.46, 0.47, 7.60, 184_700_000, 0.545, 84_100_000),
}

# ---- Executive snapshot anchors (R12M) --------------------------------------
EXEC_R12M = {
    "net_sales": 172_600_000,
    "gross_sales": 352_700_000,
    "trx": 77_886,
    "nwrx": 12_180,
    "nbrx": 6_952,
    "paid_fill_rate_90d": 0.470,
}

# ---- Switching anchors (monthly averages) -----------------------------------
SWITCH_AVG = {"to": 288, "from": 142, "net": 146}

# ---- DERM ABM districts: (name, aa_diagnosed_patients) from the PDF ----------
# Atlanta is the selected example district (0th %ile) — anchored exactly below.
DISTRICTS = [
    ("Los Angeles", 18_851), ("New Jersey", 12_929), ("New York City", 9_926),
    ("San Francisco", 9_230), ("Pacific Northwest", 7_751), ("Midwest", 7_141),
    ("Southwest", 7_140), ("Chicago", 8_400), ("Philadelphia", 7_600),
    ("Miami", 6_650), ("New England", 6_538), ("Houston", 6_457),
    ("Washington DC", 6_289), ("Dallas", 6_032), ("Phoenix", 5_600),
    ("Denver", 5_200), ("Minneapolis", 4_900), ("San Diego", 4_600),
    ("Detroit", 4_300), ("Atlanta", 4_213),
]
# Subnational conversion rates (peer averages from the PDF) + Atlanta exacts.
CONV_TREATED = 0.564   # AA treated / AA diagnosed (peer avg)
CONV_JAK = 0.068       # JAK treated / AA treated (peer avg)
CONV_BRAND = 0.623     # Brand1 / JAK treated (peer avg)
ATLANTA_EXACT = {"diagnosed": 4213, "treated": 2433, "jak": 267, "brand": 181}

# ---- Products / treatment classes (JAK class landscape in AA) ----------------
# (product, manufacturer, treatment_class, class_group, is_jak, is_ours)
PRODUCTS = [
    ("Brand1", "Pfizer", "Oral JAKs", "JAK", True, True),
    ("Olumiant", "Lilly", "Oral JAKs", "JAK", True, False),
    ("Leqselvi", "Sun Pharma", "Oral JAKs", "JAK", True, False),
    ("Other Oral JAKs", "Various", "Oral JAKs", "JAK", True, False),
    ("Opzelura", "Incyte", "Topical Anti-inflammatory", "Topical", False, False),
    ("Dupixent", "Sanofi/Regeneron", "Oral Immunomodulators", "Systemic", False, False),
    ("Oral Corticosteroids", "Various", "Oral Corticosteroids", "Systemic", False, False),
    ("Injectable Corticosteroids", "Various", "Injectable Corticosteroids", "Systemic", False, False),
    ("Topical Corticosteroids", "Various", "Topical Corticosteroids", "Topical", False, False),
    ("Topical Other", "Various", "Topical Other", "Topical", False, False),
]

REGIONS = ["Northeast", "Southeast", "Midwest", "Southwest", "West", "Pacific"]
SPECIALTIES = ["Dermatology", "Dermatology", "Dermatology", "Allergy/Immunology", "Primary Care"]


@register
class Brand1AA(BaseGenerator):
    name = "brand1_aa"
    description = "Brand1 (Alopecia Areata) commercial raw tables for the ARGOS dashboard (brand_id=1)."

    def generate_tables(self) -> dict[str, list[dict[str, Any]]]:
        self.messy = str(self.opt("clean", "false")).lower() != "true"
        self.months_back = int(self.opt("months", 24))
        n_hcps = self.config.count

        self._month_list = self._months(self.months_back)
        districts = self._alignment_rows()

        brand = self._brand_master()
        products = self._product_master()
        geo = self._geo_master()
        alignment = districts["alignment"]
        bridge = districts["bridge"]

        epi = self._epi()
        elaad_claims = self._elaad_claims(districts["stats"])
        persistency = self._persistency()
        finance = self._finance()
        npa = self._npa()
        spp = self._spp_hub()
        switching = self._switching()
        projected = self._projected_patients()
        atu = self._hcp_atu()
        xponent, hcps = self._xponent(n_hcps, districts["stats"])

        return {
            "raw_brand_master": brand,
            "raw_product_master": products,
            "raw_geo_master": geo,
            "raw_geo_alignment": alignment,
            "raw_geo_alignment_bridge": bridge,
            "raw_epi": epi,
            "raw_elaad_claims": elaad_claims,
            "raw_elaad_persistency": persistency,
            "raw_finance": finance,
            "raw_npa": npa,
            "raw_spp_hub": spp,
            "raw_pld_switching": switching,
            "raw_pld_projected": projected,
            "raw_hcp_atu": atu,
            "raw_xponent": xponent,
        }

    # ---- helpers ------------------------------------------------------------
    def _months(self, n: int) -> list[str]:
        today = date.today().replace(day=1)
        y, m, out = today.year, today.month, []
        for _ in range(n):
            out.append(f"{y:04d}-{m:02d}")
            m -= 1
            if m == 0:
                y, m = y - 1, 12
        out.reverse()
        return out

    def _weeks(self, n: int) -> list[str]:
        # ISO-ish yyyy-Www ending near today, weekly
        out = []
        y, w = date.today().isocalendar()[0], date.today().isocalendar()[1]
        for _ in range(n):
            out.append(f"{y:04d}-W{w:02d}")
            w -= 1
            if w == 0:
                y, w = y - 1, 52
        out.reverse()
        return out

    def _noise(self, lo=0.9, hi=1.1) -> float:
        return self.rng.uniform(lo, hi)

    # ---- masters ------------------------------------------------------------
    def _brand_master(self) -> list[dict[str, Any]]:
        return [{
            "brand_id": BRAND_ID,
            "brand_name": BRAND_NAME,
            "molecule": "ritlecitinib",
            "indication": "Alopecia Areata",
            "franchise": "Dermatology",
            "alignment_type": "DERM_ABM",
            "lifecycle_status": "In-line",
        }]

    def _product_master(self) -> list[dict[str, Any]]:
        return [{
            "product_id": f"PRD-{i+1:03d}",
            "brand_id": BRAND_ID if is_ours else None,
            "product_name": name,
            "manufacturer": mfr,
            "treatment_class": tclass,
            "class_group": cgroup,
            "is_jak": is_jak,
            "is_owned_brand": is_ours,
        } for i, (name, mfr, tclass, cgroup, is_jak, is_ours) in enumerate(PRODUCTS)]

    def _geo_master(self) -> list[dict[str, Any]]:
        rows = [{"geo_id": "US", "geo_name": "National", "level_name": "National", "parent_geo_id": None}]
        for r in REGIONS:
            rows.append({"geo_id": f"REG-{r[:3].upper()}", "geo_name": r,
                         "level_name": "Region", "parent_geo_id": "US"})
        # a handful of ZIP3s per region as the universal finest grain
        for r in REGIONS:
            for z in range(3):
                zip3 = f"{self.rng.randint(100, 999)}"
                rows.append({"geo_id": f"ZIP-{zip3}", "geo_name": f"ZIP3 {zip3}",
                             "level_name": "ZIP3", "parent_geo_id": f"REG-{r[:3].upper()}"})
        return rows

    def _alignment_rows(self) -> dict[str, Any]:
        """DERM ABM alignment: National → District → (implicit territories).
        Returns alignment rows, base-geo bridge, and per-district claim stats."""
        alignment = [{
            "align_id": "ABM-NATIONAL", "brand_id": BRAND_ID, "alignment_type": "DERM_ABM",
            "align_name": "National", "level_name": "National", "level_no": 0,
            "parent_align_id": None,
        }]
        bridge, stats = [], {}
        for i, (name, aa_diag) in enumerate(DISTRICTS):
            align_id = f"ABM-{i+1:03d}"
            alignment.append({
                "align_id": align_id, "brand_id": BRAND_ID, "alignment_type": "DERM_ABM",
                "align_name": f"DERM ABM {name}", "level_name": "District", "level_no": 1,
                "parent_align_id": "ABM-NATIONAL",
            })
            # map each district to a couple of base ZIP3s (illustrative)
            for _ in range(2):
                bridge.append({"align_id": align_id, "geo_id": f"ZIP-{self.rng.randint(100, 999)}"})
            stats[align_id] = {"name": name, "aa_diagnosed": aa_diag}
        return {"alignment": alignment, "bridge": bridge, "stats": stats}

    # ---- facts --------------------------------------------------------------
    def _epi(self) -> list[dict[str, Any]]:
        rows = []
        year = date.today().year
        for scenario, a in FUNNEL_ANCHORS.items():
            seeking, rx, sysm, jak, lit, fill, dot, grev, gtn, nrev = a
            rows.append({
                "brand_id": BRAND_ID, "year": year, "scenario": scenario,
                "pts_seeking_tx": seeking,
                "rx_written_pct": rx, "systemic_written_pct": sysm,
                "jak_written_pct": jak, "brand1_written_pct": lit,
                "fill_rate_90d": fill, "avg_annual_dot": dot,
                "gross_revenue": grev, "gtn_pct": gtn, "net_revenue": nrev,
                # derived absolute step patients (so the funnel reconciles)
                "rx_written": round(seeking * rx),
                "systemic_written": round(seeking * rx * sysm),
                "jak_written": round(seeking * rx * sysm * jak),
                "brand1_written": round(seeking * rx * sysm * jak * lit),
                "prevalence": 700_000, "indication_pct": 0.89, "prophylactic_tx_rate": 0.12,
            })
        return rows

    def _elaad_claims(self, stats: dict[str, Any]) -> list[dict[str, Any]]:
        """Monthly patient claims per DERM ABM district (C12M drives subnational)."""
        rows = []
        for align_id, s in stats.items():
            if s["name"] == "Atlanta":
                diag, treated = ATLANTA_EXACT["diagnosed"], ATLANTA_EXACT["treated"]
                jak, brand = ATLANTA_EXACT["jak"], ATLANTA_EXACT["brand"]
            else:
                diag = s["aa_diagnosed"]
                treated = round(diag * CONV_TREATED * self._noise(0.85, 1.2))
                jak = round(treated * CONV_JAK * self._noise(0.7, 1.6))
                brand = round(jak * CONV_BRAND * self._noise(0.8, 1.15))
            dot = round(7.6 * self._noise(0.95, 1.05), 2)
            for month in self._month_list:
                mf = self._noise(0.95, 1.05) / 12  # spread annual across months
                rows.append({
                    "brand_id": BRAND_ID, "month": month, "align_id": align_id,
                    "aa_diagnosed_pts": round(diag * mf, 1),
                    "aa_treated_pts": round(treated * mf, 1),
                    "jak_treated_pts": round(jak * mf, 1),
                    "brand_treated_pts": round(brand * mf, 1),
                    "avg_annual_dot": dot,
                })
        return rows

    def _persistency(self) -> list[dict[str, Any]]:
        rows = []
        for cohort_year in (date.today().year - 2, date.today().year - 1, date.today().year):
            decay = self.rng.uniform(0.90, 0.94)
            remaining = 1.0
            for m in range(0, 13):
                if m > 0:
                    remaining *= decay
                rows.append({
                    "brand_id": BRAND_ID, "cohort_year": cohort_year,
                    "months_since_init": m, "pct_remaining": round(remaining, 4),
                })
        return rows

    def _finance(self) -> list[dict[str, Any]]:
        """Monthly gross/net sales; last 12 months sum ≈ EXEC_R12M."""
        rows = []
        last12 = self._month_list[-12:]
        # base monthly net with mild upward trend + seasonality
        weights = [1 + 0.03 * i + 0.1 * math.sin(i / 12 * 2 * math.pi) for i in range(len(self._month_list))]
        wsum_last12 = sum(weights[-12:])
        gtn = 1 - EXEC_R12M["net_sales"] / EXEC_R12M["gross_sales"]
        for i, month in enumerate(self._month_list):
            share = weights[i] / wsum_last12
            net = EXEC_R12M["net_sales"] * share * self._noise(0.97, 1.03)
            gross = net / (1 - gtn)
            rows.append({
                "brand_id": BRAND_ID, "month": month, "scenario": "Actual",
                "gross_sales": round(gross, 2), "net_sales": round(net, 2),
                "gtn_pct": round(gtn, 4),
            })
        # OP26 budget monthly line (full-year plan spread evenly)
        for month in last12:
            rows.append({
                "brand_id": BRAND_ID, "month": month, "scenario": "OP26 Budget",
                "gross_sales": round(FUNNEL_ANCHORS["OP26 Budget"][7] / 12, 2),
                "net_sales": round(FUNNEL_ANCHORS["OP26 Budget"][9] / 12, 2),
                "gtn_pct": FUNNEL_ANCHORS["OP26 Budget"][8],
            })
        return rows

    def _npa(self) -> list[dict[str, Any]]:
        """Weekly + monthly Rx, factored + non-factored. Monthly non-factored sums ≈ EXEC_R12M."""
        rows = []
        last12 = self._month_list[-12:]
        w = [self._noise(0.9, 1.1) for _ in last12]
        wsum = sum(w)
        for i, month in enumerate(last12):
            share = w[i] / wsum
            trx = EXEC_R12M["trx"] * share
            nbrx = EXEC_R12M["nbrx"] * share
            nwrx = EXEC_R12M["nwrx"] * share
            nrx = trx * 0.32
            for factored in (False, True):
                fmul = 1.18 if factored else 1.0  # factored projects to universe
                rows.append({
                    "brand_id": BRAND_ID, "period": month, "period_grain": "MONTH",
                    "is_factored": factored,
                    "trx": round(trx * fmul, 1), "nrx": round(nrx * fmul, 1),
                    "nbrx": round(nbrx * fmul, 1), "nwrx": round(nwrx * fmul, 1),
                })
        # weekly non-factored for trend (last 52 weeks)
        for week in self._weeks(52):
            share = self._noise(0.8, 1.2) / 52
            rows.append({
                "brand_id": BRAND_ID, "period": week, "period_grain": "WEEK",
                "is_factored": False,
                "trx": round(EXEC_R12M["trx"] * share, 1),
                "nrx": round(EXEC_R12M["trx"] * share * 0.32, 1),
                "nbrx": round(EXEC_R12M["nbrx"] * share, 1),
                "nwrx": round(EXEC_R12M["nwrx"] * share, 1),
            })
        return rows

    def _spp_hub(self) -> list[dict[str, Any]]:
        rows = []
        rate = EXEC_R12M["paid_fill_rate_90d"]
        for week in self._weeks(52):
            eligible = round(EXEC_R12M["nbrx"] / 52 * self._noise(0.8, 1.2))
            paid = round(eligible * rate * self._noise(0.95, 1.05))
            fills = round(eligible * self._noise(1.0, 1.3))
            r = {
                "brand_id": BRAND_ID, "week": week,
                "scripts_received": fills, "eligible_scripts": eligible,
                "paid_fills_90d": paid,
                "paid_fill_rate_90d": round(paid / eligible, 4) if eligible else 0.0,
            }
            if self.messy and self.rng.random() < 0.01:
                r["paid_fills_90d"] = -abs(r["paid_fills_90d"])  # reversal to be cleaned
            rows.append(r)
        return rows

    def _switching(self) -> list[dict[str, Any]]:
        """Monthly from/to matrix centred on Brand1 → avg to≈288, from≈142, net≈146."""
        counterparties = [p[0] for p in PRODUCTS if p[0] != "Brand1"]
        rows = []
        for month in self._month_list:
            for direction, total in (("TO", SWITCH_AVG["to"]), ("FROM", SWITCH_AVG["from"])):
                # split total across counterparties
                weights = [self.rng.random() for _ in counterparties]
                wsum = sum(weights)
                for cp, wt in zip(counterparties, weights):
                    rows.append({
                        "brand_id": BRAND_ID, "month": month, "focus_product": "Brand1",
                        "direction": direction, "counterparty_product": cp,
                        "specialty": "All",
                        "switch_patients": round(total * wt / wsum * self._noise(0.85, 1.15), 1),
                    })
        return rows

    def _projected_patients(self) -> list[dict[str, Any]]:
        classes = sorted({p[2] for p in PRODUCTS})
        rows = []
        for month in self._month_list:
            base = {c: self.rng.uniform(500, 4000) for c in classes}
            total = sum(base.values())
            for c, v in base.items():
                rows.append({
                    "brand_id": BRAND_ID, "month": month, "treatment_class": c,
                    "projected_patients": round(v, 1),
                    "class_share_pct": round(v / total, 4),
                })
        return rows

    def _hcp_atu(self) -> list[dict[str, Any]]:
        rows = []
        year = date.today().year
        for q in (1, 2, 3, 4):
            rows.append({
                "brand_id": BRAND_ID, "year": year, "quarter": f"Q{q}",
                "jak_written_pct": round(0.53 * self._noise(0.97, 1.03), 4),
                "brand1_written_pct": round(0.46 * self._noise(0.97, 1.03), 4),
                "specialty": "Dermatology",
            })
        return rows

    def _xponent(self, n_hcps: int, stats: dict[str, Any]) -> tuple[list, list]:
        align_ids = list(stats.keys())
        hcps = []
        for i in range(max(n_hcps, 1)):
            hcps.append({
                "hcp_id": f"HCP-{i+1:06d}",
                "npi": f"{self.rng.randint(1000000000, 1999999999)}",
                "hcp_name": self.faker.name(),
                "specialty": self.rng.choice(SPECIALTIES),
                "align_id": self.rng.choice(align_ids),
                "decile": self.rng.randint(1, 10),
            })
        rows = []
        last3 = self._month_list[-3:]
        for h in hcps:
            base = self.rng.lognormvariate(1.2, 0.9) * (h["decile"] / 5)
            for month in last3:
                trx = round(base * self._noise(0.8, 1.2), 1)
                rows.append({
                    "brand_id": BRAND_ID, "month": month, "hcp_id": h["hcp_id"],
                    "align_id": h["align_id"], "specialty": h["specialty"],
                    "product_name": "Brand1",
                    "trx": trx, "nrx": round(trx * 0.35, 1), "nbrx": round(trx * 0.12, 1),
                })
        return rows, hcps
