"""Callable-credential contract for the context-length metadata probes.

``resolve_runtime_provider()`` hands back a **callable** token provider — not a
string — for the ``key_cmd`` and Entra ID auth paths, because gateways that
issue short-lived bearers (Databricks AI Gateway, internal OIDC brokers) go
stale mid-session and 401. Both wire clients invoke that callable per request.

``agent.model_metadata`` is the other half of the problem: its probes build
``requests``/``httpx`` calls by hand AND fingerprint the credential for cache
keys, so a callable reaching them raised, verbatim from a ``key_cmd`` session::

    AttributeError: 'CommandTokenSource' object has no attribute 'encode'

from ``_codex_oauth_token_fingerprint`` — surfaced in the web UI as a bare
"Error: 'CommandTokenSource' object has no attribute 'encode'". The sibling
failure modes are ``.startswith()`` on the Anthropic ``sk-ant-oat`` check and
the provider object landing in an ``Authorization`` header value.

These assert the behavior contract — a real token reaches the wire, a mint
failure degrades instead of raising, and no callable survives into a header —
not the call shape.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def offline_requests(monkeypatch):
    """Make every probe's HTTP call fail fast, with no real network.

    The point of these tests is that a callable credential never raises
    ``AttributeError`` on the way to the wire — not that any catalog answers.
    A connection error is the honest offline outcome and keeps the resolver on
    its documented fallback path.
    """
    import agent.model_metadata as mm

    mm._ensure_requests()

    class _Boom(Exception):
        pass

    def _no_network(*_a, **_kw):
        raise _Boom("offline")

    monkeypatch.setattr(mm.requests, "get", _no_network, raising=False)
    monkeypatch.setattr(mm.requests, "post", _no_network, raising=False)
    return _Boom


def _provider(token: str = "minted-token"):
    """A minimal stand-in for ``CommandTokenSource``: callable, not a str."""

    class _TokenProvider:
        def __init__(self):
            self.calls = 0

        def __call__(self):
            self.calls += 1
            return token

    return _TokenProvider()


class TestMaterializedApiKey:
    def test_string_key_is_stripped(self):
        from agent.model_metadata import _materialized_api_key

        assert _materialized_api_key("  sk-key  ") == "sk-key"

    def test_none_becomes_empty(self):
        from agent.model_metadata import _materialized_api_key

        assert _materialized_api_key(None) == ""

    def test_callable_is_minted_not_stringified(self):
        from agent.model_metadata import _materialized_api_key

        tp = _provider("  minted  ")
        assert _materialized_api_key(tp) == "minted"
        assert tp.calls == 1, "the provider must be invoked, not stringified"

    def test_mint_failure_degrades_to_empty(self):
        """A metadata probe is best-effort — a miss falls back to a default.

        Raising would turn a momentarily-unavailable token helper into a failed
        session start, which is strictly worse than an unverified context
        window.
        """
        from agent.model_metadata import _materialized_api_key

        def _boom():
            raise RuntimeError("token command exited 1")

        assert _materialized_api_key(_boom) == ""

    def test_non_string_mint_result_is_rejected(self):
        from agent.model_metadata import _materialized_api_key

        assert _materialized_api_key(lambda: object()) == ""

    def test_unsupported_type_is_not_stringified(self):
        """``str(obj)`` would yield a repr long enough to pass as a credential."""
        from agent.model_metadata import _materialized_api_key

        assert _materialized_api_key(object()) == ""


class TestAuthHeadersMintTheToken:
    def test_callable_yields_a_bearer_of_the_minted_token(self):
        from agent.model_metadata import _auth_headers

        assert _auth_headers(_provider("tok-abc")) == {
            "Authorization": "Bearer tok-abc"
        }

    def test_failing_provider_sends_no_auth_header_at_all(self):
        """Better to probe unauthenticated than to send a broken header."""
        from agent.model_metadata import _auth_headers

        def _boom():
            raise RuntimeError("helper down")

        assert _auth_headers(_boom) == {}

    def test_no_callable_survives_into_a_header_value(self):
        from agent.model_metadata import _auth_headers

        for value in _auth_headers(_provider()).values():
            assert isinstance(value, str)
            assert "TokenProvider" not in value


class TestCodexFingerprintAcceptsAProvider:
    """The reported crash: hashing the credential for an in-process cache key."""

    def test_codex_context_resolution_does_not_raise_on_a_callable(
        self, offline_requests
    ):
        from agent.model_metadata import (
            _resolve_codex_oauth_context_length_with_source,
        )

        ctx, source = _resolve_codex_oauth_context_length_with_source(
            "gpt-5.5", access_token=_provider("tok-abc")
        )
        # Offline: the live probe can't answer, so the static table does. The
        # contract under test is "no AttributeError", not the number itself.
        assert source in {"live", "memory", "fallback"}
        assert ctx is None or ctx > 0

    def test_two_mints_of_the_same_provider_share_a_cache_key(self):
        """Fingerprinting must key on the minted token, not the object.

        A provider that returns a stable token must not miss its own cache
        entry on the second call, or every probe re-hits the network.
        """
        from agent.model_metadata import _codex_oauth_token_fingerprint
        from agent.model_metadata import _materialized_api_key

        tp = _provider("stable-token")
        first = _codex_oauth_token_fingerprint(_materialized_api_key(tp))
        second = _codex_oauth_token_fingerprint(_materialized_api_key(tp))
        assert first == second

    def test_empty_credential_short_circuits_before_the_fingerprint(
        self, offline_requests
    ):
        from agent.model_metadata import (
            _fetch_codex_oauth_context_lengths_with_source,
        )

        def _boom():
            raise RuntimeError("helper down")

        assert _fetch_codex_oauth_context_lengths_with_source(_boom) == ({}, False)


class TestAnthropicProbeAcceptsAProvider:
    def test_oauth_shaped_minted_token_is_still_detected(self, offline_requests):
        """The ``sk-ant-oat`` check must run on the minted value.

        ``.startswith()`` on the provider object raised AttributeError; treating
        the object as a non-OAuth key would instead send a doomed request.
        """
        from agent.model_metadata import _query_anthropic_context_length

        assert (
            _query_anthropic_context_length(
                "claude-x",
                "https://api.anthropic.invalid",
                _provider("sk-ant-oat-xyz"),
            )
            is None
        )

    def test_failing_provider_does_not_raise(self, offline_requests):
        from agent.model_metadata import _query_anthropic_context_length

        def _boom():
            raise RuntimeError("helper down")

        assert (
            _query_anthropic_context_length(
                "claude-x", "https://api.anthropic.invalid", _boom
            )
            is None
        )


class TestPublicEntryPointAcceptsAProvider:
    """``get_model_context_length`` is what every caller actually reaches."""

    @pytest.mark.parametrize(
        "provider", ["openai-codex", "anthropic", "custom", "ollama", ""]
    )
    def test_callable_api_key_resolves_a_context_window(
        self, provider, offline_requests
    ):
        from agent.model_metadata import get_model_context_length

        ctx = get_model_context_length(
            model="some-model",
            base_url="https://gw.example.invalid/v1",
            api_key=_provider("tok-abc"),
            provider=provider,
        )
        assert isinstance(ctx, int) and ctx > 0

    def test_explicit_override_wins_without_minting(self):
        """The override short-circuit must not spend a token mint."""
        from agent.model_metadata import get_model_context_length

        tp = _provider()
        ctx = get_model_context_length(
            model="some-model",
            base_url="https://gw.example.invalid/v1",
            api_key=tp,
            config_context_length=4096,
            provider="custom",
        )
        assert ctx == 4096
        assert tp.calls == 0

    @pytest.mark.parametrize(
        "model,base_url,provider",
        [
            # The two branches that let the AttributeError escape the resolver
            # entirely (no surrounding try/except), which is how it reached the
            # web UI as a bare "Error: ...has no attribute 'encode'".
            ("claude-opus-4", "https://api.anthropic.com", "anthropic"),
            ("gpt-5.5", "https://chatgpt.com/backend-api/codex", "openai-codex"),
        ],
    )
    def test_unguarded_probe_branches_do_not_propagate(
        self, model, base_url, provider, offline_requests
    ):
        from agent.model_metadata import get_model_context_length

        ctx = get_model_context_length(
            model=model,
            base_url=base_url,
            api_key=_provider("tok-abc"),
            provider=provider,
        )
        assert isinstance(ctx, int) and ctx > 0
