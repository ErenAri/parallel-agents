"""Smoke tests for the polish slice: settings store, env precedence, and module imports."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(repo_root / "src"))

    from parallel_agents.desktop.services.settings_store import (
        KNOWN_KEYS,
        SettingsStore,
    )

    # --- 1. user file round-trip ---
    with tempfile.TemporaryDirectory() as user_home:
        os.environ["HOME"] = user_home
        os.environ["USERPROFILE"] = user_home
        # clear so we know what came back
        for key in KNOWN_KEYS:
            os.environ.pop(key, None)

        store = SettingsStore(project_root=None)
        path = store.save_user(
            {
                "PA_PLANNER_MODEL": "sonnet",
                "PA_DESKTOP_LLM_BRIEF": "1",
                "ignored_key": "evil",  # must be filtered out
            }
        )
        assert path.exists()
        raw = json.loads(path.read_text(encoding="utf-8"))
        assert raw == {"PA_PLANNER_MODEL": "sonnet", "PA_DESKTOP_LLM_BRIEF": "1"}
        print(f"user file written: {path.name}")

        # clear env, then reload -> env should pick up file values
        for key in KNOWN_KEYS:
            os.environ.pop(key, None)
        loaded = store.load()
        assert os.environ["PA_PLANNER_MODEL"] == "sonnet"
        assert os.environ["PA_DESKTOP_LLM_BRIEF"] == "1"
        assert loaded.user == {"PA_PLANNER_MODEL": "sonnet", "PA_DESKTOP_LLM_BRIEF": "1"}
        assert loaded.project == {}
        print("user load applied to env: ok")

        # --- 2. project overrides user ---
        with tempfile.TemporaryDirectory() as proj_tmp:
            proj_root = Path(proj_tmp)
            (proj_root / ".parallel-agents").mkdir()
            (proj_root / ".parallel-agents" / "desktop.json").write_text(
                json.dumps({"PA_PLANNER_MODEL": "opus", "PA_JUDGE_MODEL": "opus"}),
                encoding="utf-8",
            )

            for key in KNOWN_KEYS:
                os.environ.pop(key, None)
            store_p = SettingsStore(project_root=proj_root)
            loaded_p = store_p.load()
            # project wins for PA_PLANNER_MODEL
            assert os.environ["PA_PLANNER_MODEL"] == "opus"
            # user-only key still present
            assert os.environ["PA_DESKTOP_LLM_BRIEF"] == "1"
            # project-only key present
            assert os.environ["PA_JUDGE_MODEL"] == "opus"
            assert loaded_p.project["PA_PLANNER_MODEL"] == "opus"
            print("project overrides user: ok")

    # --- 3. malformed file does not crash and does not pollute env ---
    with tempfile.TemporaryDirectory() as user_home:
        os.environ["HOME"] = user_home
        os.environ["USERPROFILE"] = user_home
        bad = Path(user_home) / ".parallel-agents-desktop.json"
        bad.write_text("{not json", encoding="utf-8")
        store = SettingsStore(project_root=None)
        for key in KNOWN_KEYS:
            os.environ.pop(key, None)
        loaded = store.load()
        assert loaded.user == {}
        for key in KNOWN_KEYS:
            assert key not in os.environ
        print("malformed file ignored cleanly: ok")

    # --- 4. status bar LLM indicator ---
    for key in KNOWN_KEYS:
        os.environ.pop(key, None)
    from parallel_agents.desktop.services.status import llm_indicator_text

    assert llm_indicator_text() == "LLM: deterministic"
    os.environ["PA_DESKTOP_LLM_BRIEF"] = "1"
    os.environ["PA_DESKTOP_LLM_RFC"] = "1"
    assert llm_indicator_text() == "LLM: brief, rfc"
    print(f"LLM indicator text: {llm_indicator_text()}")

    # --- 5. history store: round-trip, de-dup, cap, malformed file ---
    from parallel_agents.desktop.services.history import DEFAULT_LIMIT, HistoryStore

    with tempfile.TemporaryDirectory() as tmp:
        hist_path = Path(tmp) / "history.json"
        hist = HistoryStore(path=hist_path)

        assert hist.get("repo_path") == []
        assert hist.add("repo_path", "  ") == []  # blank ignored

        hist.add("repo_path", "C:/projects/alpha")
        hist.add("repo_path", "C:/projects/beta")
        assert hist.get("repo_path") == ["C:/projects/beta", "C:/projects/alpha"]

        # re-add moves to front without duplication
        hist.add("repo_path", "C:/projects/alpha")
        assert hist.get("repo_path") == ["C:/projects/alpha", "C:/projects/beta"]

        # cap at DEFAULT_LIMIT entries
        for i in range(DEFAULT_LIMIT + 3):
            hist.add("repo_ref", f"owner/repo-{i}")
        capped = hist.get("repo_ref")
        assert len(capped) == DEFAULT_LIMIT
        assert capped[0] == f"owner/repo-{DEFAULT_LIMIT + 2}"

        # keys are independent
        assert hist.get("repo_path") == ["C:/projects/alpha", "C:/projects/beta"]

        hist.clear("repo_path")
        assert hist.get("repo_path") == []
        assert len(hist.get("repo_ref")) == DEFAULT_LIMIT

        # malformed file degrades to empty, then recovers on next add
        hist_path.write_text("{not json", encoding="utf-8")
        assert hist.get("repo_ref") == []
        assert hist.add("repo_ref", "owner/fresh") == ["owner/fresh"]
        print("history store round-trip/de-dup/cap: ok")

    # --- 6. engine roadmap_milestones helper ---
    from parallel_agents.desktop.services.engine import EngineService
    from parallel_agents.project_office import office_output_dir

    with tempfile.TemporaryDirectory() as proj_tmp:
        engine = EngineService()
        assert engine.roadmap_milestones(None) == []

        engine.init_project(proj_tmp, name="smoke")
        assert engine.roadmap_milestones("no-such-run") == []

        run_dir = office_output_dir(Path(proj_tmp)) / "run-smoke" / "company"
        run_dir.mkdir(parents=True)
        roadmap = {
            "name": "Smoke Roadmap",
            "horizon_weeks": 6,
            "outcomes": ["ship"],
            "items": [
                {"id": "R1", "title": "a", "owner_role": "eng", "milestone": "M1"},
                {"id": "R2", "title": "b", "owner_role": "eng", "milestone": "M2"},
                {"id": "R3", "title": "c", "owner_role": "eng", "milestone": "M1"},
                {"id": "R4", "title": "d", "owner_role": "eng", "milestone": "  "},
            ],
        }
        (run_dir / "roadmap.json").write_text(json.dumps(roadmap), encoding="utf-8")
        assert engine.roadmap_milestones("run-smoke") == ["M1", "M2"]
        print("engine roadmap_milestones ordered/unique/empty: ok")

    print("\nOK: polish slice smoke tests pass.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
