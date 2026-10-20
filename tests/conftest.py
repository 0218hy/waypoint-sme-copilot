"""Test defaults: no network model. The voice uses a deterministic composer that writes each beat's
key plus its required placeholders (so grounding is still checked); free text uses code understanding
unless a test injects a decider. Document reading replays gold labels for the synthetic sample only."""

from __future__ import annotations

from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True)
def _no_network_model(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    from agent import llm, voice

    monkeypatch.setenv("WAYPOINT_LLM_PROVIDER", "none")
    monkeypatch.setenv("WAYPOINT_READER_REPLAY", "1")
    voice.set_test_composer(voice.echo_composer)
    llm.set_test_decider(None)
    yield
    voice.set_test_composer(None)
    llm.set_test_decider(None)
