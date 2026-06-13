"""Tests for the desktop LLM layer: enablement policy, structured-output
plumbing, the string-coercion fix, and engine provenance/fallback."""

from __future__ import annotations

import json
import types

import pytest

from parallel_agents.desktop.services import llm_config
from parallel_agents.desktop.services.llm import call_anthropic_tool, str_list


# -- llm_config enablement precedence ----------------------------------------

def _clear_llm_env(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("PA_DESKTOP_LLM", raising=False)
    for key in llm_config.ARTIFACTS:
        monkeypatch.delenv(f"PA_DESKTOP_LLM_{key}", raising=False)


def test_llm_disabled_without_key(monkeypatch):
    _clear_llm_env(monkeypatch)
    assert llm_config.llm_enabled("BRIEF") is False
    assert llm_config.active_generators() == []


def test_llm_default_on_with_key(monkeypatch):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert llm_config.llm_enabled("ROADMAP") is True
    assert len(llm_config.active_generators()) == len(llm_config.ARTIFACTS)


def test_per_artifact_flag_overrides_key(monkeypatch):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("PA_DESKTOP_LLM_BRIEF", "0")
    assert llm_config.llm_enabled("BRIEF") is False
    assert llm_config.llm_enabled("RFC") is True  # others still default-on


def test_global_flag_overrides_key_but_not_per_artifact(monkeypatch):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("PA_DESKTOP_LLM", "0")
    assert llm_config.llm_enabled("SPRINT") is False
    monkeypatch.setenv("PA_DESKTOP_LLM_SPRINT", "1")
    assert llm_config.llm_enabled("SPRINT") is True  # per-artifact wins over global


def test_flag_enables_without_key(monkeypatch):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("PA_DESKTOP_LLM_BRIEF", "yes")
    assert llm_config.llm_enabled("BRIEF") is True


def test_force_off_flag_round_trips_through_settings_store(tmp_path, monkeypatch):
    """A user must be able to force a generator OFF even with a key present.
    Validates the '0' flag survives settings persistence and disables the LLM."""
    from parallel_agents.desktop.services.settings_store import SettingsStore

    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    store = SettingsStore(project_root=None)
    store.save_user({"PA_DESKTOP_LLM_BRIEF": "0"})

    # reload from disk into the environment
    monkeypatch.delenv("PA_DESKTOP_LLM_BRIEF", raising=False)
    store.load()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")  # key present, but...

    assert llm_config.llm_enabled("BRIEF") is False  # explicit force-off wins
    assert llm_config.llm_enabled("RFC") is True  # others still default-on


# -- str_list: the character-explosion fix -----------------------------------

def test_str_list_does_not_explode_strings():
    # The old `list("increase adoption")` bug produced ['i','n','c',...].
    assert str_list("increase adoption", ["fallback"]) == ["increase adoption"]


def test_str_list_passes_through_lists_and_trims():
    assert str_list(["a", " b ", "", None], ["fb"]) == ["a", "b"]


def test_str_list_falls_back_on_empty_or_wrong_type():
    assert str_list([], ["fb"]) == ["fb"]
    assert str_list(None, ["fb"]) == ["fb"]
    assert str_list({"k": "v"}, ["fb"]) == ["fb"]  # dict is not a list[str]


# -- call_anthropic_tool plumbing (fake SDK) ---------------------------------

class _FakeBlock:
    def __init__(self, name, data):
        self.type = "tool_use"
        self.name = name
        self.input = data


class _FakeResponse:
    def __init__(self, name, data):
        self.content = [_FakeBlock(name, data)]


class _FakeMessages:
    def __init__(self, capture):
        self._capture = capture

    def create(self, **kwargs):
        self._capture.update(kwargs)
        name = kwargs["tool_choice"]["name"]
        # Echo a payload that matches the requested tool.
        return _FakeResponse(name, {"echoed": True})


class _FakeClient:
    def __init__(self, capture):
        self.messages = _FakeMessages(capture)
        self._capture = capture

    def with_options(self, **kwargs):
        self._capture["with_options"] = kwargs
        return self


def _install_fake_anthropic(monkeypatch, capture):
    fake_mod = types.ModuleType("anthropic")
    fake_mod.Anthropic = lambda api_key=None: _FakeClient(capture)
    monkeypatch.setitem(__import__("sys").modules, "anthropic", fake_mod)


def test_call_anthropic_tool_forces_tool_and_sets_timeout(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("PA_DESKTOP_LLM_MODEL", "claude-sonnet-4-6")
    capture: dict = {}
    _install_fake_anthropic(monkeypatch, capture)

    data, model = call_anthropic_tool(
        "hi",
        tool_name="emit_thing",
        tool_description="desc",
        input_schema={"type": "object", "properties": {}},
    )
    assert data == {"echoed": True}
    assert model == "claude-sonnet-4-6"
    # forced tool choice + a bounded timeout/retry
    assert capture["tool_choice"] == {"type": "tool", "name": "emit_thing"}
    assert capture["with_options"]["max_retries"] == 1
    assert capture["with_options"]["timeout"] > 0


def test_call_anthropic_tool_raises_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        call_anthropic_tool(
            "hi", tool_name="x", tool_description="d", input_schema={"type": "object"}
        )


# -- generator mapping (fake call_anthropic_tool) ----------------------------

def test_generate_llm_brief_maps_structured_output(monkeypatch):
    from parallel_agents.desktop.services import llm_brief

    def fake_tool(prompt, **kwargs):
        return (
            {
                "title": "Smart Garden",
                "problem_statement": "Plants die when owners travel.",
                "goals": ["Automate watering", "Alert on low moisture"],
                # exercise the coercion guard: a string where a list is expected
                "target_users": "Apartment gardeners",
            },
            "claude-sonnet-4-6",
        )

    monkeypatch.setattr(llm_brief, "call_anthropic_tool", fake_tool)
    brief, model = llm_brief.generate_llm_brief("a smart garden", title="Garden")
    assert model == "claude-sonnet-4-6"
    assert brief.title == "Smart Garden"
    assert brief.goals == ["Automate watering", "Alert on low moisture"]
    # string did NOT explode into characters
    assert brief.target_users == ["Apartment gardeners"]


def test_generate_llm_roadmap_uses_llm_items(monkeypatch):
    from parallel_agents.company_workflows import create_product_brief
    from parallel_agents.desktop.services import llm_roadmap

    def fake_tool(prompt, **kwargs):
        return (
            {
                "outcomes": ["Ship MVP"],
                "items": [
                    {"title": "Build watering controller", "owner_role": "Eng", "milestone": "M1"},
                    {"title": "Moisture sensor integration", "owner_role": "Eng", "milestone": "M2"},
                ],
            },
            "claude-sonnet-4-6",
        )

    monkeypatch.setattr(llm_roadmap, "call_anthropic_tool", fake_tool)
    brief = create_product_brief("a smart garden", title="Garden")
    roadmap, _ = llm_roadmap.generate_llm_roadmap(brief, horizon_weeks=8)
    titles = [i.title for i in roadmap.items]
    assert titles == ["Build watering controller", "Moisture sensor integration"]
    # NOT the deterministic template's fixed RM-01..RM-04 about parallel-agents
    assert all("parallel" not in t.lower() for t in titles)


def test_generate_llm_roadmap_raises_on_empty_items_not_template(monkeypatch):
    """Returning no usable items must NOT pass the deterministic template off as
    LLM output — it must raise so provenance is recorded as template."""
    from parallel_agents.company_workflows import create_product_brief
    from parallel_agents.desktop.services import llm_roadmap

    def fake_tool(prompt, **kwargs):
        return ({"outcomes": ["x"], "items": []}, "claude-sonnet-4-6")

    monkeypatch.setattr(llm_roadmap, "call_anthropic_tool", fake_tool)
    brief = create_product_brief("a smart garden", title="Garden")
    with pytest.raises(RuntimeError):
        llm_roadmap.generate_llm_roadmap(brief, horizon_weeks=8)


def test_engine_roadmap_empty_llm_falls_back_with_template_provenance(tmp_path, monkeypatch):
    """End-to-end: an LLM roadmap that yields no items is recorded as template,
    never as LLM (the headline 'template theater' guarantee)."""
    from parallel_agents.desktop.services import llm_roadmap
    from parallel_agents.desktop.services.engine import EngineService

    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("PA_DESKTOP_LLM_ROADMAP", "1")
    monkeypatch.setenv("PA_DESKTOP_LLM_BRIEF", "0")  # keep brief deterministic

    def fake_tool(prompt, **kwargs):
        return ({"items": []}, "claude-sonnet-4-6")

    monkeypatch.setattr(llm_roadmap, "call_anthropic_tool", fake_tool)

    eng = EngineService()
    eng.init_project(str(tmp_path), name="RM")
    brief = eng.create_brief("a smart garden", title="Garden")
    result = eng.create_roadmap(brief.run_id, horizon_weeks=8)
    assert result.provenance["generator"] == "template"
    assert "llm-error" in result.provenance["reason"]


# -- engine provenance + fallback --------------------------------------------

def test_engine_records_template_provenance_without_key(tmp_path, monkeypatch):
    from parallel_agents.desktop.services.engine import EngineService

    _clear_llm_env(monkeypatch)
    eng = EngineService()
    eng.init_project(str(tmp_path), name="Prov")
    result = eng.create_brief("an idea", title="T")
    assert result.provenance["generator"] == "template"
    assert result.provenance["reason"] == "no-api-key"

    # provenance is recorded in the artifact audit chain
    from parallel_agents.company_artifacts import load_company_artifact_events
    from parallel_agents.project_office import office_output_dir

    events = load_company_artifact_events(
        office_output_dir(tmp_path), result.run_id, "brief"
    )
    created = [e for e in events if e["payload"].get("event") == "created"]
    assert created and created[0]["payload"]["provenance"]["generator"] == "template"


def test_engine_uses_llm_when_enabled(tmp_path, monkeypatch):
    from parallel_agents.desktop.services import llm_brief
    from parallel_agents.desktop.services.engine import EngineService
    from parallel_agents.company_workflows import create_product_brief

    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("PA_DESKTOP_LLM_BRIEF", "1")  # force on, no real key needed

    def fake_generate(idea, *, title=None):
        b = create_product_brief(idea, title=title)
        b.title = "LLM Title"
        return b, "claude-sonnet-4-6"

    monkeypatch.setattr(llm_brief, "generate_llm_brief", fake_generate)

    eng = EngineService()
    eng.init_project(str(tmp_path), name="LLM")
    result = eng.create_brief("an idea", title="T")
    assert result.provenance == {"generator": "llm", "model": "claude-sonnet-4-6"}
    brief_data = json.loads(result.artifact_path.read_text(encoding="utf-8"))
    assert brief_data["title"] == "LLM Title"


def test_engine_falls_back_and_logs_on_llm_error(tmp_path, monkeypatch):
    from parallel_agents.desktop.services import llm_brief
    from parallel_agents.desktop.services.engine import EngineService

    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("PA_DESKTOP_LLM_BRIEF", "1")

    def boom(idea, *, title=None):
        raise RuntimeError("network down")

    monkeypatch.setattr(llm_brief, "generate_llm_brief", boom)

    eng = EngineService()
    eng.init_project(str(tmp_path), name="Boom")
    result = eng.create_brief("an idea", title="T")
    assert result.provenance["generator"] == "template"
    assert "llm-error" in result.provenance["reason"]
    # deterministic content was still produced
    brief_data = json.loads(result.artifact_path.read_text(encoding="utf-8"))
    assert brief_data["title"] == "T"
