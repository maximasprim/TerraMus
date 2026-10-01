"""Pure unit tests for the production-safety helpers (no database)."""
from app.core import security_checks as sc


def test_mock_payments_default_on_for_dev_and_test_environments():
    assert sc.mock_payments_enabled("development", None, "anything") is True
    assert sc.mock_payments_enabled("test", None, "anything") is True


def test_mock_payments_default_off_for_any_production_like_environment():
    for env in ("production", "prod", "staging", "aws", "PRODUCTION"):
        assert sc.mock_payments_enabled(env, None, "s" * 40) is False


def test_mock_payments_in_production_need_explicit_opt_in_and_a_strong_secret():
    assert sc.mock_payments_enabled("production", True, "s" * 40) is True
    assert sc.mock_payments_enabled("production", True, "short") is False
    assert sc.mock_payments_enabled("production", True, "mock-payment-secret-change-me") is False
    assert sc.mock_payments_enabled("production", True, "replace-with-a-long-random-value") is False


def test_explicit_false_always_wins():
    assert sc.mock_payments_enabled("development", False, "x") is False


def test_client_ip_ignores_forwarded_header_unless_proxies_are_trusted():
    assert sc.resolve_client_ip("6.6.6.6, 9.9.9.9", "10.0.0.1", 0) == "10.0.0.1"
    assert sc.resolve_client_ip(None, None, 0) == "unknown"


def test_client_ip_uses_the_entry_the_trusted_proxy_appended_not_the_spoofable_left():
    # a client can send any X-Forwarded-For it likes; the balancer appends the real peer on the right
    assert sc.resolve_client_ip("6.6.6.6, 9.9.9.9", "10.0.0.1", 1) == "9.9.9.9"
    assert sc.resolve_client_ip("spoofed, real-client, lb-hop", "p", 2) == "real-client"


def test_client_ip_falls_back_to_peer_when_header_is_shorter_than_trusted_hops():
    assert sc.resolve_client_ip("7.7.7.7", "10.0.0.1", 2) == "10.0.0.1"


def test_startup_warnings_only_for_production_like_environments():
    assert sc.security_warnings("development", "change-me-in-env", "x", None) == []
    warnings = sc.security_warnings("production", "change-me-in-env", "x", None)
    assert len(warnings) == 1 and "JWT_SECRET" in warnings[0]
    assert sc.security_warnings("production", "j" * 40, "s" * 40, None) == []
