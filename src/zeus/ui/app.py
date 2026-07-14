"""Streamlit UI for interactive zeus data generation.

Thin form over the same primitives ``zeus generate`` uses: pick a use case
from the registry, fill in a :class:`~zeus.core.base.GeneratorConfig`, call
``generate_tables()``, and write the result with the same
:mod:`zeus.core.writer` the CLI calls. Launch with ``zeus ui`` (see
``zeus/src/zeus/cli.py``) or directly via ``streamlit run src/zeus/ui/app.py``.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import streamlit as st

from zeus import generators as _generators  # noqa: F401  (registers use cases)
from zeus.core import GeneratorConfig, all_generators, get
from zeus.core.writer import FORMATS, write_tables

# UI-only metadata describing each generator's `-o key=value` options. Use
# cases not listed here fall back to a free-text key=value box, so nothing
# is unsupported — this only adds friendlier controls for the known ones.
OPTION_SPECS = {
    "patient_history": [
        ("clean", "checkbox", False, "Disable messy/dirty rows"),
    ],
    "pharma_sales": [
        ("months", "number", 36, "Months of FX/sales history"),
        ("clean", "checkbox", False, "Disable messy/dirty rows"),
    ],
    "example_users": [
        ("domain", "text", "example.com", "Email domain for generated users"),
    ],
}


def render_options(use_case: str) -> dict[str, str]:
    specs = OPTION_SPECS.get(use_case)
    opts: dict[str, str] = {}
    if not specs:
        raw = st.text_area(
            "Advanced options (key=value, one per line)",
            key=f"opt_raw_{use_case}",
            help="Same shape as the CLI's -o key=value flag.",
        )
        for line in raw.splitlines():
            line = line.strip()
            if line and "=" in line:
                k, v = line.split("=", 1)
                opts[k.strip()] = v.strip()
        return opts

    for key, kind, default, help_text in specs:
        widget_key = f"opt_{use_case}_{key}"
        if kind == "checkbox":
            opts[key] = "true" if st.checkbox(help_text, value=default, key=widget_key) else "false"
        elif kind == "number":
            opts[key] = str(int(st.number_input(help_text, value=default, step=1, key=widget_key)))
        elif kind == "text":
            opts[key] = st.text_input(help_text, value=default, key=widget_key)
    return opts


def bundle_bytes(result: dict) -> bytes:
    if result["fmt"] == "sqlite":
        return Path(result["paths"][0]).read_bytes()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in result["paths"]:
            zf.write(p, arcname=Path(p).name)
    return buf.getvalue()


def bundle_name(result: dict) -> str:
    if result["fmt"] == "sqlite":
        return f"{result['use_case']}.db"
    return f"{result['use_case']}_{result['fmt']}.zip"


def main() -> None:
    st.set_page_config(page_title="Zeus — Synthetic Data Generator", page_icon="⚡")
    st.title("⚡ Zeus")
    st.caption("Synthetic data generator for the Hermes MCP stack")

    gens = all_generators()
    if not gens:
        st.error("No generators registered.")
        st.stop()

    use_case = st.sidebar.selectbox("Use case", sorted(gens))
    st.sidebar.caption(gens[use_case].description)

    with st.form("generate_form"):
        count = st.number_input(
            "Count", min_value=1, value=100, step=1,
            help="Number of records — meaning varies by use case (see sidebar description).",
        )

        seed_col, value_col = st.columns(2)
        use_seed = seed_col.checkbox("Deterministic (fixed seed)", value=False)
        seed = value_col.number_input("Seed", value=42, step=1, disabled=not use_seed)

        fmt = st.selectbox("Format", FORMATS, index=FORMATS.index("sqlite"))
        out_dir = st.text_input("Output directory", value=f"output/{use_case}")

        st.markdown("**Options**")
        opts = render_options(use_case)

        submitted = st.form_submit_button("Generate", type="primary")

    if submitted:
        cfg = GeneratorConfig(count=int(count), seed=int(seed) if use_seed else None, options=opts)
        tables = get(use_case)(cfg).generate_tables()
        paths = write_tables(tables, Path(out_dir), fmt, db_name=use_case)
        st.session_state.result = {
            "use_case": use_case,
            "fmt": fmt,
            "tables": tables,
            "paths": paths,
            "out_dir": out_dir,
        }

    result = st.session_state.get("result")
    if result:
        st.success(
            f"Generated {result['use_case']} → {result['out_dir']} "
            f"({len(result['tables'])} table(s))"
        )
        st.table({
            "table": list(result["tables"]),
            "rows": [len(rows) for rows in result["tables"].values()],
        })

        preview = st.selectbox("Preview table", list(result["tables"]), key="preview_table")
        st.dataframe(result["tables"][preview][:50])

        st.download_button(
            "Download",
            data=bundle_bytes(result),
            file_name=bundle_name(result),
            mime="application/octet-stream",
        )


main()
