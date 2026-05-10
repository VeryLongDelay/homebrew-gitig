import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_formula_sha.py"


class FormulaHookTests(unittest.TestCase):
    def run_script(self, formula_text: str) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as tmpdir:
            formula_path = Path(tmpdir) / "gitig.rb"
            formula_path.write_text(formula_text, encoding="utf8")
            return subprocess.run(
                ["python3", str(SCRIPT_PATH), str(formula_path)],
                capture_output=True,
                text=True,
                check=False,
            )

    def test_rejects_placeholder_sha(self) -> None:
        result = self.run_script(
            'class Gitig < Formula\n  sha256 "REPLACE_ME"\nend\n'
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("placeholder sha256", result.stderr)

    def test_rejects_missing_sha(self) -> None:
        result = self.run_script(
            'class Gitig < Formula\n  url "https://example.com/archive.tar.gz"\nend\n'
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing a valid sha256 line", result.stderr)

    def test_accepts_real_sha(self) -> None:
        result = self.run_script(
            'class Gitig < Formula\n  sha256 "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"\nend\n'
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
