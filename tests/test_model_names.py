"""The model names live in one place, and nothing can run on a model we cannot price.

THE FAILURE THIS GUARDS AGAINST IS SILENT AND EXPENSIVE. A model string changed in one file while
`PRICES_PER_MTOK` still holds the old rate means every cost figure the admin pages print, every
projection, and every alert threshold is quietly wrong - and nothing errors, because the cost code
looks the model up and gets a number. It gets the WRONG number. Haiku 4.5 to 5.5 was a tenfold
price drop, so a stale entry would have overstated the rashifal bill by 10x; the next change could
as easily understate it.
"""
import os
import re
from pathlib import Path

import pytest

from app.ai import config as ai_config
from app.rashifal import config as rashifal_config

ROOT = Path(__file__).resolve().parents[1]


def test_every_current_model_has_a_price():
    for role, model in ai_config.CURRENT.items():
        assert model in ai_config.PRICES_PER_MTOK, f"{role} -> {model} is not priced"


def test_every_configured_model_has_a_price(monkeypatch):
    """The three workloads, at their defaults."""
    for name in ("REPORT_MODEL", "CHAT_MODEL", "RASHIFAL_MODEL"):
        monkeypatch.delenv(name, raising=False)
    models = [ai_config.get_settings().model,
              ai_config.get_chat_settings().model,
              rashifal_config.get_rashifal_settings().model]
    for model in models:
        assert model in ai_config.PRICES_PER_MTOK, model
        assert ai_config.estimate_cost_usd(model, {"input_tokens": 1000,
                                                   "output_tokens": 1000}) is not None


def test_the_defaults_are_the_current_generation(monkeypatch):
    """A workload left on a previous-generation model is a decision, not an accident - so it has to
    be visible here rather than buried in a default somewhere."""
    for name in ("REPORT_MODEL", "CHAT_MODEL", "RASHIFAL_MODEL"):
        monkeypatch.delenv(name, raising=False)
    assert ai_config.get_settings().model == ai_config.CURRENT["sonnet"]
    assert ai_config.get_chat_settings().model == ai_config.CURRENT["sonnet"]
    assert rashifal_config.get_rashifal_settings().model == ai_config.CURRENT["haiku"]


def test_no_module_spells_a_model_name_that_config_should_own():
    """MODEL NAMES IN ONE PLACE, as asked.

    app/ai/config.py owns CURRENT and the price table; app/ai/client.py names the models that lack
    adaptive thinking, which is a capability fact and not a choice of model. Everywhere else in
    app/ should read one of those rather than spell a model string, or the next migration has to
    find them all again.
    """
    allowed = {"app/ai/config.py", "app/ai/client.py"}
    offenders = []
    for path in sorted((ROOT / "app").rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        if rel in allowed:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"[\"']claude-[a-z0-9-]+[\"']", line):
                offenders.append(f"{rel}:{number}")
    assert not offenders, f"model names spelled outside {sorted(allowed)}: {offenders}"


def test_the_deploy_example_matches_the_defaults():
    """The example is what gets copied onto the server. If it names a previous-generation model the
    code has moved off, the deployment silently keeps running the old one."""
    text = (ROOT / "deploy/env.production.example").read_text(encoding="utf-8")
    for var, expected in (("REPORT_MODEL", ai_config.CURRENT["sonnet"]),
                          ("CHAT_MODEL", ai_config.CURRENT["sonnet"]),
                          ("RASHIFAL_MODEL", ai_config.CURRENT["haiku"])):
        found = re.search(rf"^{var}=(\S+)$", text, re.M)
        assert found, f"{var} is not in the deploy example"
        assert found.group(1) == expected, f"{var}={found.group(1)}, expected {expected}"


@pytest.mark.parametrize("model", sorted(ai_config.PRICES_PER_MTOK))
def test_no_priced_model_is_a_date_suffixed_variant(model):
    """The IDs are complete as given; a date suffix is a model that does not exist."""
    assert not re.search(r"-20\d{6}$", model), model


def test_haiku_5_5_is_known_to_have_thinking_and_effort():
    """The capability set is named models, never a family prefix - Haiku 5.5 is the first Haiku with
    adaptive thinking and effort, so `startswith("claude-haiku")` silently strips both. That test
    was in the chat path while the report path had already been fixed."""
    from app.ai.client import MODELS_WITHOUT_THINKING

    assert ai_config.CURRENT["haiku"] not in MODELS_WITHOUT_THINKING
    assert "claude-haiku-4-5" in MODELS_WITHOUT_THINKING
