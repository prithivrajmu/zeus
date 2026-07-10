# Zeus ⚡

Build 1 of the Hermes stack: a **pluggable synthetic data generator** producing **raw source tables** for ETL/ELT pipelines that build downstream mart tables. Each use case is a small self-registering generator class emitting multiple related tables with real referential integrity; the framework handles seeding, per-use-case options, and output formats (`json`, `jsonl`, `csv`, `sqlite`).

## The Two Use Cases

**`patient_history`** — patient history tracking at a US insurance firm. Six raw tables: `raw_members`, `raw_policies`, `raw_providers`, `raw_claims`, `raw_claim_lines` (ICD-10 diagnoses + CPT procedures + billed/allowed/paid), `raw_prescriptions` (NDC codes, fills, copays). `--count` = number of members; claims/lines/rx volumes scale from it. Chronic members generate recurring claims and monthly maintenance-drug fills.

**`pharma_sales`** — pharma brand sales across countries. Five raw tables: `raw_products` (brands, molecules, therapeutic areas, launch/patent years), `raw_countries`, `raw_distributors`, `raw_fx_rates` (monthly currency→USD), `raw_sales` (monthly sell-in **in local currency** — FX normalization is deliberately left to the pipeline). `--count` = number of sales transactions. Built-in seasonality, no pre-launch sales, loss-of-exclusivity decay.

**ETL bait:** both use cases inject ~1% messy rows (negative amounts, case drift, trailing spaces in country codes) so the pipeline has real cleaning work. Disable with `-o clean=true`.

## Install

```bash
cd zeus
pip install -e .
```

## Usage

```bash
zeus list
zeus generate patient_history -n 500 --seed 42 -f sqlite    # → output/patient_history/patient_history.db (6 tables)
zeus generate patient_history -n 500 -f csv                 # → output/patient_history/*.csv
zeus generate pharma_sales -n 20000 --seed 42 -f sqlite     # → output/pharma_sales/pharma_sales.db (5 tables)
zeus generate pharma_sales -n 20000 -o months=48            # 4 years of history
zeus generate pharma_sales -n 20000 -o clean=true           # no messy rows
```

## Adding a New Use Case

1. Copy `src/zeus/generators/example.py` (single-table) or model on `patient_history.py` (multi-table raw sources)
2. Rename the class, set a unique `name` and `description`
3. Single table: implement `generate()`. Multi-table: implement `generate_tables()` returning `{table_name: [records]}` with consistent foreign keys
4. Import the module in `src/zeus/generators/__init__.py`

Use `self.faker` (realistic values), `self.rng` (seeded randomness), and `self.opt("key", default)` (CLI `-o key=value` options).

## Layout

```
zeus/
├── pyproject.toml
├── src/zeus/
│   ├── cli.py               # typer CLI: list / generate
│   ├── core/
│   │   ├── base.py          # BaseGenerator + GeneratorConfig
│   │   ├── registry.py      # @register plugin registry
│   │   └── writer.py        # json / jsonl / csv / sqlite writers
│   └── generators/          # ← one module per use case
│       ├── example.py           # single-table template
│       ├── patient_history.py   # use case 1: US insurance raw tables
│       └── pharma_sales.py      # use case 2: global pharma sales raw tables
├── tests/
└── output/                  # generated datasets (gitignored)
```
