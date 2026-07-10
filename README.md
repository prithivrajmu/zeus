# Zeus ⚡

Build 1 of the Hermes stack: a **pluggable synthetic data generator**. Each use case is a small self-registering generator class; the framework handles seeding, per-use-case options, and output formats (`json`, `jsonl`, `csv`, `sqlite`) — sqlite being the friendliest format for zaia (the MCP server) to query later.

## Install

```bash
cd zeus
pip install -e .
```

## Usage

```bash
zeus list                                        # show available use cases
zeus generate example_users -n 500 --seed 42     # deterministic run
zeus generate example_users -f sqlite            # → output/example_users.db
zeus generate example_users -o domain=acme.io    # per-use-case option
```

## Adding a New Use Case

1. Copy `src/zeus/generators/example.py` to `src/zeus/generators/<use_case>.py`
2. Rename the class, set a unique `name` and a `description`
3. Implement `generate()` — yield plain dicts, using `self.faker` (realistic values), `self.rng` (seeded randomness), and `self.opt("key", default)` (CLI options)
4. Import the module in `src/zeus/generators/__init__.py`

That's it — the `@register` decorator wires it into the CLI automatically.

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
│       └── example.py       # template (replace with the two real use cases)
├── tests/
└── output/                  # generated datasets (gitignored)
```
