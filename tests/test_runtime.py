import json
import os
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest
import schedule

from storage import Store


@pytest.mark.parametrize(
    "failure", [sqlite3.OperationalError("locked"), OSError("private path")]
)
def test_watch_recovers_from_initial_and_later_storage_failures(
    monkeypatch, capsys, failure
):
    import main

    outcomes = iter([failure, {"status": "success"}, failure, {"status": "success"}])
    calls = []

    def run(*args, **kwargs):
        outcome = next(outcomes)
        calls.append(outcome)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    scheduler = schedule.Scheduler()

    def tick(_):
        if len(calls) == 4:
            raise KeyboardInterrupt
        for job in scheduler.jobs:
            job.next_run = datetime.min

    monkeypatch.setattr(main, "run_pipeline", run)
    monkeypatch.setattr(main.schedule, "Scheduler", lambda: scheduler)
    monkeypatch.setattr(main.time, "sleep", tick)
    assert main.main(["--watch", "--sources", "github"]) == 0
    output = capsys.readouterr().out
    assert [json.loads(line)["status"] for line in output.splitlines()] == [
        "error",
        "success",
        "error",
        "success",
    ]
    assert "private path" not in output


def test_scheduler_configuration_failure_is_json(capsys):
    import main

    assert main.main(["--sources", "unknown"]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "error"


def test_latest_exposes_newer_failed_collection_without_relabeling_saved_analysis(
    tmp_path,
):
    from cli import latest

    store = Store(tmp_path)
    store.save_result(
        {
            "schema_version": 2,
            "analysis_version": 5,
            "status": "success",
            "processed_at": "2026-10-20T00:00:00+00:00",
            "selected_sources": ["github"],
            "leads": [{"post_id": "github:1"}],
        },
        "latest_analysis.json",
    )
    store.record_run({"status": "error", "timestamp": "2026-10-21T00:00:00+00:00"})
    result = latest("leads", store=store)
    assert result["status"] == "success"
    assert result["analysis_status"] == "success"
    assert result["selected_sources"] == ["github"]
    assert result["latest_collection"]["status"] == "error"
    assert result["collection_newer_than_analysis"] is True


@pytest.mark.parametrize(
    "explicit,exported", [(False, False), (True, False), (True, True)]
)
def test_installed_config_reads_dotenv_with_environment_precedence(
    tmp_path, explicit, exported
):
    # A standalone module directory simulates the installed site-packages layout.
    installed = tmp_path / "installed"
    installed.mkdir()
    shutil.copy(Path(__file__).resolve().parents[1] / "config.py", installed)
    env = {k: v for k, v in os.environ.items() if not k.startswith("METIS_")}
    env["PYTHONPATH"] = str(installed)
    env_path = tmp_path / ("custom.env" if explicit else ".env")
    env_path.write_text(
        f"METIS_SOURCES=github\nMETIS_DATA_DIR={tmp_path / 'evidence'}\n"
    )
    if explicit:
        env["METIS_ENV_FILE"] = str(env_path)
        (tmp_path / ".env").write_text("METIS_SOURCES=reddit,x\n")
    if exported:
        env["METIS_SOURCES"] = "hackernews"
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import config, json; print(json.dumps({'sources': config.Settings().sources, 'data': str(config.DATA_DIR)}))",
        ],
        cwd=tmp_path,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    value = json.loads(result.stdout)
    assert value["sources"] == (["hackernews"] if exported else ["github"])
    assert value["data"] == str(tmp_path / "evidence")
