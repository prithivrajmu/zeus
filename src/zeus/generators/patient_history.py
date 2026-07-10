"""Use case 1: patient history tracking at a US insurance firm.

Emits RAW source tables (the "extract" side of an ETL/ELT pipeline) with
consistent foreign keys, ready to be staged and modeled into marts
(e.g. member_360, claims_cost_by_diagnosis, provider_performance):

    raw_members        one row per insured member (PII-style fields, all fake)
    raw_policies       plan enrollment spans per member (members can switch plans)
    raw_providers      physicians / facilities with NPI-style ids
    raw_claims         claim headers: member x provider x dates x status
    raw_claim_lines    line items per claim: ICD-10 diagnosis + CPT procedure + costs
    raw_prescriptions  pharmacy fills: NDC-style codes, drug names, copays

`--count` controls the number of members; downstream volumes scale from it
(claims ≈ 4x members, lines ≈ 2.2x claims, rx ≈ 3x members).

Raw-table realism knobs: a small % of claim lines carry messy values
(negative allowed amounts, uppercase/lowercase drift in status) so the
ETL layer has something to clean. Disable with -o clean=true.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from zeus.core import BaseGenerator, register

US_STATES = ["CA", "TX", "FL", "NY", "PA", "IL", "OH", "GA", "NC", "MI", "NJ", "WA", "AZ", "MA", "TN"]
PLAN_TYPES = ["HMO", "PPO", "EPO", "HDHP", "POS"]
PLAN_TIERS = ["bronze", "silver", "gold", "platinum"]

SPECIALTIES = [
    "Family Medicine", "Internal Medicine", "Cardiology", "Endocrinology",
    "Orthopedics", "Dermatology", "Psychiatry", "Oncology", "Pediatrics",
    "Emergency Medicine", "Physical Therapy", "Radiology",
]

# (ICD-10 code, description, chronic?)
DIAGNOSES = [
    ("E11.9", "Type 2 diabetes mellitus without complications", True),
    ("I10", "Essential (primary) hypertension", True),
    ("E78.5", "Hyperlipidemia, unspecified", True),
    ("J45.909", "Unspecified asthma, uncomplicated", True),
    ("F41.1", "Generalized anxiety disorder", True),
    ("F32.9", "Major depressive disorder, single episode", True),
    ("M54.5", "Low back pain", False),
    ("J06.9", "Acute upper respiratory infection", False),
    ("N39.0", "Urinary tract infection", False),
    ("S93.401A", "Sprain of ankle, initial encounter", False),
    ("R51.9", "Headache, unspecified", False),
    ("K21.9", "Gastro-esophageal reflux disease", True),
    ("M17.11", "Unilateral primary osteoarthritis, right knee", True),
    ("Z00.00", "General adult medical examination", False),
]

# (CPT code, description, base allowed amount)
PROCEDURES = [
    ("99213", "Office visit, established patient, low complexity", 110.0),
    ("99214", "Office visit, established patient, moderate complexity", 165.0),
    ("99203", "Office visit, new patient", 150.0),
    ("80053", "Comprehensive metabolic panel", 48.0),
    ("83036", "Hemoglobin A1c", 42.0),
    ("80061", "Lipid panel", 55.0),
    ("93000", "Electrocardiogram, complete", 85.0),
    ("71046", "Chest X-ray, 2 views", 120.0),
    ("73721", "MRI lower extremity joint", 950.0),
    ("97110", "Therapeutic exercise, 15 min", 65.0),
    ("90837", "Psychotherapy, 60 min", 175.0),
    ("36415", "Venipuncture", 12.0),
    ("90686", "Influenza vaccine, quadrivalent", 38.0),
]

# (NDC-style code, drug, strength, monthly cost, treats_chronic)
DRUGS = [
    ("00093-7214", "Metformin HCl", "500 mg", 14.0, "E11.9"),
    ("00071-0155", "Atorvastatin", "20 mg", 18.0, "E78.5"),
    ("00591-0405", "Lisinopril", "10 mg", 11.0, "I10"),
    ("00173-0682", "Albuterol inhaler", "90 mcg", 55.0, "J45.909"),
    ("00378-1805", "Sertraline", "50 mg", 16.0, "F32.9"),
    ("59762-1740", "Escitalopram", "10 mg", 19.0, "F41.1"),
    ("00186-5020", "Omeprazole", "20 mg", 13.0, "K21.9"),
    ("50111-0434", "Meloxicam", "15 mg", 12.0, "M17.11"),
    ("68180-0512", "Amoxicillin", "500 mg", 15.0, None),
    ("00054-0450", "Prednisone", "10 mg", 10.0, None),
]

CLAIM_STATUSES = ["approved", "approved", "approved", "denied", "pending", "adjusted"]
CLAIM_TYPES = ["professional", "professional", "institutional", "pharmacy_medical"]
DENIAL_REASONS = ["not_covered", "prior_auth_required", "duplicate", "out_of_network", "coding_error"]


@register
class PatientHistory(BaseGenerator):
    name = "patient_history"
    description = "US insurance raw tables: members, policies, providers, claims, claim lines, prescriptions."

    def generate_tables(self) -> dict[str, list[dict[str, Any]]]:
        n_members = self.config.count
        n_providers = max(10, n_members // 20)
        messy = str(self.opt("clean", "false")).lower() != "true"

        providers = self._providers(n_providers)
        members = self._members(n_members)
        policies = self._policies(members)
        claims, claim_lines = self._claims(members, providers, policies, messy)
        prescriptions = self._prescriptions(members, providers, messy)

        return {
            "raw_members": members,
            "raw_policies": policies,
            "raw_providers": providers,
            "raw_claims": claims,
            "raw_claim_lines": claim_lines,
            "raw_prescriptions": prescriptions,
        }

    # ------------------------------------------------------------------ dims

    def _providers(self, n: int) -> list[dict[str, Any]]:
        rows = []
        for i in range(n):
            state = self.rng.choice(US_STATES)
            rows.append({
                "provider_id": f"PRV-{i+1:05d}",
                "npi": str(self.rng.randint(1_000_000_000, 1_999_999_999)),
                "provider_name": f"Dr. {self.faker.name()}",
                "specialty": self.rng.choice(SPECIALTIES),
                "practice_name": f"{self.faker.last_name()} {self.rng.choice(['Medical Group', 'Clinic', 'Health Center', 'Associates'])}",
                "city": self.faker.city(),
                "state": state,
                "in_network": self.rng.random() < 0.85,
                "accepting_new_patients": self.rng.random() < 0.7,
            })
        return rows

    def _members(self, n: int) -> list[dict[str, Any]]:
        rows = []
        for i in range(n):
            dob = self.faker.date_of_birth(minimum_age=18, maximum_age=85)
            # 0-3 chronic conditions per member, skewed by age
            age = (date.today() - dob).days // 365
            k = self.rng.choices([0, 1, 2, 3], weights=[50, 28, 15, 7] if age < 50 else [25, 32, 27, 16])[0]
            chronic = self.rng.sample([d for d in DIAGNOSES if d[2]], k)
            rows.append({
                "member_id": f"MBR-{i+1:06d}",
                "first_name": self.faker.first_name(),
                "last_name": self.faker.last_name(),
                "date_of_birth": dob.isoformat(),
                "gender": self.rng.choice(["F", "M"]),
                "city": self.faker.city(),
                "state": self.rng.choice(US_STATES),
                "zip": self.faker.postcode(),
                "phone": self.faker.numerify("(###) ###-####"),
                "smoker": self.rng.random() < 0.14,
                "enrolled_since": self.faker.date_between("-8y", "-6m").isoformat(),
                "_chronic_codes": [c[0] for c in chronic],  # internal; dropped below
            })
        return rows

    def _policies(self, members: list[dict]) -> list[dict[str, Any]]:
        rows = []
        pid = 0
        for m in members:
            start = date.fromisoformat(m["enrolled_since"])
            # 1-3 consecutive policy spans (plan switches at renewal)
            n_spans = self.rng.choices([1, 2, 3], weights=[55, 32, 13])[0]
            for s in range(n_spans):
                pid += 1
                end = start + timedelta(days=365)
                is_current = s == n_spans - 1
                tier = self.rng.choice(PLAN_TIERS)
                rows.append({
                    "policy_id": f"POL-{pid:07d}",
                    "member_id": m["member_id"],
                    "plan_type": self.rng.choice(PLAN_TYPES),
                    "plan_tier": tier,
                    "monthly_premium": round({"bronze": 320, "silver": 450, "gold": 610, "platinum": 780}[tier]
                                             * self.rng.uniform(0.85, 1.2), 2),
                    "deductible": {"bronze": 7000, "silver": 4500, "gold": 1800, "platinum": 500}[tier],
                    "oop_max": {"bronze": 9100, "silver": 8000, "gold": 5500, "platinum": 3000}[tier],
                    "effective_date": start.isoformat(),
                    "termination_date": None if is_current else end.isoformat(),
                    "status": "active" if is_current else "terminated",
                })
                start = end
        return rows

    # ----------------------------------------------------------------- facts

    def _claims(self, members, providers, policies, messy) -> tuple[list, list]:
        by_member = {}
        for p in policies:
            by_member.setdefault(p["member_id"], []).append(p)

        claims, lines = [], []
        cid = lid = 0
        for m in members:
            chronic = m["_chronic_codes"]
            n_claims = self.rng.randint(2, 6) + 2 * len(chronic)
            for _ in range(n_claims):
                cid += 1
                svc_date = self.faker.date_between(date.fromisoformat(m["enrolled_since"]), "today")
                provider = self.rng.choice(providers)
                status = self.rng.choice(CLAIM_STATUSES)
                claim_id = f"CLM-{cid:08d}"
                claims.append({
                    "claim_id": claim_id,
                    "member_id": m["member_id"],
                    "policy_id": self.rng.choice(by_member[m["member_id"]])["policy_id"],
                    "provider_id": provider["provider_id"],
                    "claim_type": self.rng.choice(CLAIM_TYPES),
                    "service_date": svc_date.isoformat(),
                    "received_date": (svc_date + timedelta(days=self.rng.randint(1, 21))).isoformat(),
                    "status": (status.upper() if messy and self.rng.random() < 0.05 else status),
                    "denial_reason": self.rng.choice(DENIAL_REASONS) if status == "denied" else None,
                })
                # 1-4 lines: chronic members bias toward their own conditions
                for _ in range(self.rng.choices([1, 2, 3, 4], weights=[40, 32, 18, 10])[0]):
                    lid += 1
                    if chronic and self.rng.random() < 0.55:
                        dx_code = self.rng.choice(chronic)
                        dx = next(d for d in DIAGNOSES if d[0] == dx_code)
                    else:
                        dx = self.rng.choice(DIAGNOSES)
                    cpt, cpt_desc, base = self.rng.choice(PROCEDURES)
                    billed = round(base * self.rng.uniform(1.1, 1.9), 2)
                    allowed = round(billed * self.rng.uniform(0.5, 0.85), 2)
                    if messy and self.rng.random() < 0.01:
                        allowed = -allowed  # dirty value for ETL to catch
                    paid = round(allowed * self.rng.uniform(0.6, 1.0), 2) if status != "denied" else 0.0
                    lines.append({
                        "claim_line_id": f"LIN-{lid:09d}",
                        "claim_id": claim_id,
                        "line_number": len([l for l in lines if l["claim_id"] == claim_id]) + 1,
                        "icd10_code": dx[0],
                        "diagnosis_desc": dx[1],
                        "cpt_code": cpt,
                        "procedure_desc": cpt_desc,
                        "billed_amount": billed,
                        "allowed_amount": allowed,
                        "paid_amount": paid,
                        "member_responsibility": round(max(allowed - paid, 0), 2),
                    })
        return claims, lines

    def _prescriptions(self, members, providers, messy) -> list[dict[str, Any]]:
        prescribers = [p for p in providers if p["specialty"] not in ("Radiology", "Physical Therapy")]
        rows = []
        rxid = 0
        for m in members:
            chronic = set(m["_chronic_codes"])
            maintenance = [d for d in DRUGS if d[4] in chronic]
            fills = []
            # monthly fills for maintenance drugs over the last year
            for drug in maintenance:
                for month_back in range(self.rng.randint(6, 12)):
                    fills.append((drug, month_back))
            # a few acute scripts
            for _ in range(self.rng.randint(0, 3)):
                fills.append((self.rng.choice([d for d in DRUGS if d[4] is None]), self.rng.randint(0, 12)))

            for (ndc, drug, strength, cost, _), month_back in fills:
                rxid += 1
                fill_date = date.today() - timedelta(days=30 * month_back + self.rng.randint(0, 6))
                rows.append({
                    "rx_id": f"RX-{rxid:08d}",
                    "member_id": m["member_id"],
                    "prescriber_id": self.rng.choice(prescribers)["provider_id"],
                    "ndc_code": ndc,
                    "drug_name": (drug.lower() if messy and self.rng.random() < 0.04 else drug),
                    "strength": strength,
                    "days_supply": self.rng.choice([30, 30, 30, 90]),
                    "fill_date": fill_date.isoformat(),
                    "drug_cost": round(cost * self.rng.uniform(0.9, 1.15), 2),
                    "member_copay": round(cost * self.rng.uniform(0.1, 0.4), 2),
                    "pharmacy_name": f"{self.faker.last_name()} Pharmacy",
                })

        # drop the internal helper column from members now that facts are built
        for m in members:
            m.pop("_chronic_codes", None)
        return rows
