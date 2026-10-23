import json
from datetime import date, timedelta

import pytest

import cli
from config import Settings
from pipeline import run_analysis
from storage import Store
from storage.research import import_research, list_research


def note(**overrides):
    return {
        "source": "ukbusinessforums",
        "url": "https://www.ukbusinessforums.co.uk/threads/example.1/",
        "locator": "opening post",
        "title": "Synthetic import test",
        "published_on": (date.today() - timedelta(days=300)).isoformat(),
        "observed_on": date.today().isoformat(),
        "audience": "small_business",
        "observation": "problem_report",
        "summary": "The analyst thinks this is a workflow problem: I would pay for an inventory app.",
        "caveat": "Synthetic test data, not a real person or observation.",
        "follow_up": "Check original evidence.",
        **overrides,
    }


def batch(tmp_path, notes):
    path = tmp_path / "notes.json"
    path.write_text(json.dumps({"schema_version": 1, "notes": notes}))
    return path


def test_import_is_idempotent_and_never_scores_analyst_text_as_a_buyer(tmp_path):
    store = Store(tmp_path / "store")
    path = batch(tmp_path, [note()])
    assert import_research(path, store)["new"] == 1
    assert import_research(path, store)["unchanged"] == 1
    result = list_research(store)
    assert result["research_notes"][0]["age_days"] == 300
    assert result["research_notes"][0]["scored_as_lead"] is False
    assert store.load_posts() == []
    assert run_analysis(Settings(sources=["hackernews"]), store)["leads"] == []


@pytest.mark.parametrize(
    "invalid",
    [
        {"url": "https://unrelated.example/threads/1"},
        {"url": "https://www.ukbusinessforums.co.uk.evil.test/threads/1"},
        {"url": "https://user@www.ukbusinessforums.co.uk/threads/1"},
        {"url": "http://www.ukbusinessforums.co.uk/threads/1"},
        {"published_on": None},
        {"observed_on": (date.today() + timedelta(days=1)).isoformat()},
        {"published_on": (date.today() + timedelta(days=1)).isoformat()},
        {"excerpt": "word " * 26},
        {"summary": "   "},
        {"verified_buyer": True},
    ],
)
def test_invalid_batch_is_rejected_atomically(tmp_path, invalid):
    store = Store(tmp_path / "store")
    path = batch(tmp_path, [note(), note(locator="second", **invalid)])
    with pytest.raises(ValueError):
        import_research(path, store)
    assert list_research(store)["total"] == 0


def test_unknown_date_is_retained_and_same_review_url_can_have_multiple_notes(tmp_path):
    store = Store(tmp_path / "store")
    path = batch(
        tmp_path,
        [note(published_on=None, date_note="Page has no year"), note(locator="reply")],
    )
    import_research(path, store)
    result = list_research(store)
    assert result["total"] == 2
    assert result["research_notes"][1]["age_days"] is None
    assert list_research(store, "capterra")["total"] == 0


def test_duplicate_import_identity_is_not_silently_overwritten(tmp_path):
    path = batch(tmp_path, [note(), note(summary="Different observation")])
    store = Store(tmp_path / "store")
    with pytest.raises(ValueError, match="Duplicate"):
        import_research(path, store)
    assert list_research(store)["total"] == 0


def test_cli_import_and_research_are_offline(tmp_path, monkeypatch, capsys):
    store = Store(tmp_path / "store")
    monkeypatch.setattr(cli, "Store", lambda: store)
    path = batch(tmp_path, [note()])
    assert cli.main(["research-import", str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["new"] == 1
    assert cli.main(["research", "--source", "ukbusinessforums"]) == 0
    assert json.loads(capsys.readouterr().out)["total"] == 1
