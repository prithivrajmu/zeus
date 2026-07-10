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
