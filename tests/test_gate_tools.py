"""Controls for scratch gate-proof helpers."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("prove_gates", ROOT / "scripts/prove_gates.py")
prove_gates = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prove_gates)


def test_run_accepts_non_utf8_stdout(tmp_path):
    script = tmp_path / "emit.py"
    script.write_text(
        "import sys\nsys.stdout.buffer.write(b'ok\\x97done\\n')\n",
        encoding="utf-8",
    )
    output = prove_gates.run(tmp_path, [str(script)], 0)
    assert "ok" in output
    assert "done" in output
