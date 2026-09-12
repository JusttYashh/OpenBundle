from openbundle.config import BindError, Settings, validate_bind


def test_loopback_ok():
    validate_bind("127.0.0.1")
    validate_bind("localhost")


def test_refuse_all_interfaces():
    try:
        validate_bind("0.0.0.0")
        raise AssertionError("should have refused")
    except BindError as exc:
        assert "127.0.0.1" in str(exc)


def test_expose_allows(monkeypatch):
    monkeypatch.delenv("OPENBUNDLE_EXPOSE", raising=False)
    validate_bind("0.0.0.0", expose=True)


def test_default_listen_is_loopback():
    assert Settings().host == "127.0.0.1"
    assert Settings().port == 4180
