import pytest

pytest.importorskip("streamlit")

from streamlit.testing.v1 import AppTest  # noqa: E402


def _app() -> AppTest:
    at = AppTest.from_file("../src/zeus/ui/app.py")
    at.run()
    assert not at.exception
    return at


def test_app_loads_with_default_use_case():
    _app()


def test_generate_populates_session_state():
    at = _app()
    at.button[0].click().run(timeout=15)
    assert not at.exception
    assert "result" in at.session_state
    assert at.session_state.result["tables"]
