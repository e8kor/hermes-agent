"""Tests for plugin CLI subcommand registration in shell completion.

Regression for: `hermes completion bash` silently omitted every plugin-registered
top-level subcommand (hermes github, hermes linkedin, …) because the `completion`
token is a builtin subcommand, so plugin CLI discovery was skipped on that path.
"""
import argparse

import pytest

from hermes_cli.main import _register_plugin_cli_subcommands, cmd_completion


@pytest.fixture
def parser():
    p = argparse.ArgumentParser(prog="hermes")
    sub = p.add_subparsers(dest="command")
    sub.add_parser("sessions")
    sub.add_parser("completion")
    return p


def _fake_cmd_info(name, subcmds=()):
    """Build a register_cli_command-style dict with a realistic setup_fn.

    A real plugin setup_fn receives the top-level subparser and builds its own
    subparser tree underneath (matching how cli.py does _setup_argparse).
    """
    def setup_fn(sp):
        subs = sp.add_subparsers(dest="subcmd")
        for sc in subcmds:
            subs.add_parser(sc)

    return {
        "name": name,
        "help": f"Help for {name}",
        "description": f"Description for {name}",
        "setup_fn": setup_fn,
        "handler_fn": None,
    }


class _FakeManager:
    _cli_commands = {"github": _fake_cmd_info("github", ["status", "repo"])}


def _subparsers_of(parser):
    return next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))


@pytest.fixture
def stub_plugin_sources(monkeypatch):
    """Point the local imports in _register_plugin_cli_subcommands at fakes."""
    import plugins.memory as pm
    import hermes_cli.plugins as hp
    import hermes_cli.main as main_mod

    monkeypatch.setattr(pm, "discover_plugin_cli_commands", lambda: [])
    monkeypatch.setattr(hp, "discover_plugins", lambda *a, **k: None)
    monkeypatch.setattr(hp, "get_plugin_manager", lambda: _FakeManager())
    monkeypatch.setattr(main_mod, "_resolve_deferred_platform_cli_command", lambda name: None)
    monkeypatch.setattr(main_mod, "_first_positional_argv", lambda: "completion")


def _stub_generators(monkeypatch):
    """generate_bash/zsh/fish are imported inside cmd_completion from
    hermes_cli.completion, so monkeypatch them at their real location."""
    import hermes_cli.completion as comp
    monkeypatch.setattr(comp, "generate_bash", lambda p: "SCRIPT")
    monkeypatch.setattr(comp, "generate_zsh", lambda p: "ZSH")
    monkeypatch.setattr(comp, "generate_fish", lambda p: "FISH")


class TestRegisterPluginCliSubcommands:
    def test_adds_plugin_command_and_subcommands(self, parser, stub_plugin_sources):
        subparsers = _subparsers_of(parser)

        _register_plugin_cli_subcommands(subparsers)

        assert "github" in subparsers.choices
        gh_sub = _subparsers_of(subparsers.choices["github"])
        assert "status" in gh_sub.choices
        assert "repo" in gh_sub.choices

    def test_leaves_builtin_commands_intact(self, parser, stub_plugin_sources):
        subparsers = _subparsers_of(parser)
        _register_plugin_cli_subcommands(subparsers)
        assert "sessions" in subparsers.choices
        assert "completion" in subparsers.choices


class TestCmdCompletion:
    def test_forces_plugin_registration_before_generate(self, parser, monkeypatch):
        registered = []

        def fake_register(subparsers):
            registered.append(True)

        monkeypatch.setattr("hermes_cli.main._register_plugin_cli_subcommands", fake_register)
        _stub_generators(monkeypatch)

        class _Args:
            shell = "bash"

        cmd_completion(_Args(), parser)

        assert registered == [True]

    def test_skips_registration_when_parser_is_none(self, monkeypatch):
        called = []
        monkeypatch.setattr(
            "hermes_cli.main._register_plugin_cli_subcommands",
            lambda sp: called.append(True),
        )
        _stub_generators(monkeypatch)

        class _Args:
            shell = "bash"

        cmd_completion(_Args(), None)

        assert called == []
