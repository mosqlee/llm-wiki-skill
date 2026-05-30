import subprocess
from datetime import datetime
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "wiki.py"
PYTHON = Path.home() / ".hermes" / "hermes-agent" / "venv" / "bin" / "python"


def run_wiki(*args):
    return subprocess.run(
        [str(PYTHON), str(SCRIPT), *args],
        text=True,
        capture_output=True,
        check=True,
    )


def test_init_creates_mvp_dirs_and_copies_templates(tmp_path):
    root = tmp_path / "wiki"

    run_wiki("init", "--path", str(root))

    for dirname in [
        "compiled/source-notes",
        "registry",
        "changelog",
        "wiki/concepts",
        "wiki/frameworks",
        "schema",
    ]:
        assert (root / dirname).is_dir()

    assert (root / "registry" / "source-registry.md").is_file()
    assert (root / "changelog" / "changes.md").is_file()
    assert (root / "schema" / "TEMPLATE.concept.md").is_file()


def test_new_id_uses_today_and_next_sequence(tmp_path):
    root = tmp_path / "wiki"
    today = datetime.now().strftime("%Y%m%d")
    notes = root / "compiled" / "source-notes"
    notes.mkdir(parents=True)
    (notes / f"src_{today}_001.md").write_text("", encoding="utf-8")
    (notes / f"src_{today}_003.md").write_text("", encoding="utf-8")

    result = run_wiki("new-id", "source", "--path", str(root))

    assert result.stdout.strip() == f"src_{today}_004"


def test_registry_lists_and_adds_rows(tmp_path):
    root = tmp_path / "wiki"
    registry = root / "registry"
    registry.mkdir(parents=True)
    path = registry / "concept-registry.md"
    path.write_text("# Concept Registry\n\n| h |\n|---|\n", encoding="utf-8")

    run_wiki(
        "registry",
        "add",
        "concept",
        "--entry",
        "| cpt_20260530_001 | Attention |",
        "--path",
        str(root),
    )
    result = run_wiki("registry", "list", "concept", "--path", str(root))

    assert "| cpt_20260530_001 | Attention |" in result.stdout


def test_changelog_add_and_pending_append_entries(tmp_path):
    root = tmp_path / "wiki"
    changelog = root / "changelog"
    changelog.mkdir(parents=True)
    (changelog / "changes.md").write_text("# Changes\n", encoding="utf-8")
    (changelog / "pending-review.md").write_text("# Pending Review\n", encoding="utf-8")

    run_wiki(
        "changelog",
        "add",
        "--change-type",
        "update",
        "--object",
        "cpt_20260530_001",
        "--summary",
        "Expanded definition",
        "--path",
        str(root),
    )
    run_wiki(
        "changelog",
        "pending",
        "--change-type",
        "review",
        "--object",
        "clm_20260530_001",
        "--summary",
        "Needs evidence check",
        "--path",
        str(root),
    )

    assert "Expanded definition" in (changelog / "changes.md").read_text(encoding="utf-8")
    assert "Needs evidence check" in (changelog / "pending-review.md").read_text(encoding="utf-8")
