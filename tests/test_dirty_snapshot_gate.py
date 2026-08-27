import importlib.util
import subprocess
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "check_acceptance_gate.py"
SPEC = importlib.util.spec_from_file_location("paper_acceptance_gate", SCRIPT)
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def test_dirty_parent_snapshot_detects_product_change(tmp_path, monkeypatch):
    _git(tmp_path, "init", "-b", "dev")
    _git(tmp_path, "config", "user.email", "paper-test@example.invalid")
    _git(tmp_path, "config", "user.name", "paper-test")
    product = tmp_path / "product.py"
    product.write_text("VALUE = 1\n", encoding="utf-8")
    _git(tmp_path, "add", "product.py")
    _git(tmp_path, "commit", "-m", "fixture")

    monkeypatch.setattr(GATE, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(GATE, "PRODUCT_SNAPSHOT_PATHS", (Path("product.py"),))

    before = GATE.capture_parent_snapshot()
    assert before["dirty"] is False
    assert GATE.parent_snapshot_equal(before, GATE.capture_parent_snapshot())

    product.write_text("VALUE = 2\n", encoding="utf-8")
    after = GATE.capture_parent_snapshot()
    assert after["dirty"] is True
    assert after["product_file_sha256"] != before["product_file_sha256"]
    assert GATE.parent_snapshot_equal(before, after) is False
