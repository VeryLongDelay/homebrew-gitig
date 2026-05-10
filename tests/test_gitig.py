import contextlib
import io
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import gitig
import gitig.cli as gitig_cli
import gitig.core as gitig_core
import gitig.spinner as gitig_spinner


class ParseArgsTests(unittest.TestCase):
    def test_parse_args_version_aliases(self) -> None:
        short = gitig.parse_args(["-v"])
        typo = gitig.parse_args(["--verison"])
        self.assertEqual(short.command, "version")
        self.assertEqual(typo.command, "version")

    def test_parse_args_accepts_clustered_flags_before_input(self) -> None:
        parsed = gitig.parse_args(["-nac", "gh:python"])
        self.assertEqual(parsed.command, "gh:python")
        self.assertTrue(parsed.append)
        self.assertTrue(parsed.no_comments)

    def test_parse_args_accepts_output_and_source_flags(self) -> None:
        parsed = gitig.parse_args(["init", "Node", "-o", "Custom.gitignore", "-s", "ghg"])
        self.assertEqual(parsed.command, "init")
        self.assertEqual(parsed.rest, ["Node"])
        self.assertEqual(parsed.output, "Custom.gitignore")
        self.assertTrue(parsed.output_explicit)
        self.assertEqual(parsed.source, "github-global")

    def test_parse_args_compact_alias(self) -> None:
        parsed = gitig.parse_args(["-c", ".gitignore"])
        self.assertEqual(parsed.command, "compact")
        self.assertEqual(parsed.rest, [".gitignore"])

    def test_parse_args_license_init_alias(self) -> None:
        parsed = gitig.parse_args(["-li", "mit", "--fullname", "Jane Doe"])
        self.assertEqual(parsed.command, "license")
        self.assertEqual(parsed.rest, ["init", "mit"])
        self.assertEqual(parsed.fullname, "Jane Doe")

    def test_parse_args_license_init_command_alias(self) -> None:
        parsed = gitig.parse_args(["li", "mit", "--fullname", "Jane Doe"])
        self.assertEqual(parsed.command, "license")
        self.assertEqual(parsed.rest, ["init", "mit"])
        self.assertEqual(parsed.fullname, "Jane Doe")

    def test_parse_args_rejects_unknown_long_flag(self) -> None:
        with self.assertRaises(gitig.UnrecognizedCommandError):
            gitig.parse_args(["--wat"])

    def test_parse_args_rejects_unknown_short_flag(self) -> None:
        with self.assertRaises(gitig.UnrecognizedCommandError):
            gitig.parse_args(["-z"])

    def test_parse_args_rejects_unknown_clustered_short_flag(self) -> None:
        with self.assertRaises(gitig.UnrecognizedCommandError):
            gitig.parse_args(["-naz"])


class TemplateResolutionTests(unittest.TestCase):
    def test_parse_template_args_applies_sticky_prefixes(self) -> None:
        self.assertEqual(
            gitig.parse_template_args(["gh:", "node,python", "tt:macos", "linux"]),
            ["gh:node", "gh:python", "tt:macos", "tt:linux"],
        )

    def test_build_init_content_rejects_mixed_providers(self) -> None:
        with self.assertRaisesRegex(ValueError, "cannot mix GitHub templates and gitignore.io templates"):
            gitig.build_init_content(["gh:Node", "tt:python"], "all", True, False)

    def test_build_init_content_for_github_sections(self) -> None:
        catalog = [gitig.CatalogEntry("github", "Node", "Node.gitignore", "Node", ["Node", "gh:Node"], "root")]
        with mock.patch.object(gitig_core, "get_catalog", return_value=catalog), mock.patch.object(
            gitig_core, "get_github_template_content", return_value="node_modules/\n"
        ):
            content = gitig.build_init_content(["gh:Node"], "github", True, False)
        self.assertEqual(content, "# --- Node ---\nnode_modules/\n")

    def test_build_init_content_for_github_no_comments(self) -> None:
        catalog = [gitig.CatalogEntry("github", "Node", "Node.gitignore", "Node", ["Node", "gh:Node"], "root")]
        with mock.patch.object(gitig_core, "get_catalog", return_value=catalog), mock.patch.object(
            gitig_core, "get_github_template_content", return_value="# heading\nnode_modules/\n"
        ):
            content = gitig.build_init_content(["gh:Node"], "github", True, True)
        self.assertEqual(content, "node_modules/\n")

    def test_build_init_content_for_gitignoreio_dedupes(self) -> None:
        catalog = [gitig.CatalogEntry("gitignoreio", "python", "python", "python", ["python", "tt:python"])]
        with mock.patch.object(gitig_core, "get_catalog", return_value=catalog), mock.patch.object(
            gitig_core, "get_gitignoreio_template_content", return_value="venv/\nvenv/\n__pycache__/\n"
        ):
            content = gitig.build_init_content(["tt:python"], "gitignoreio", True, False)
        self.assertEqual(content, "venv/\n__pycache__/\n")


class OutputTests(unittest.TestCase):
    def test_merge_appended_content_dedupes_existing_lines(self) -> None:
        self.assertEqual(
            gitig.merge_appended_content("foo\nbar\n", "bar\nbaz\n"),
            "foo\nbar\nbaz\n",
        )

    def test_write_generated_content_writes_new_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / ".gitignore"
            gitig.write_generated_content(str(output), "node_modules/\n", False, False)
            self.assertEqual(output.read_text("utf8"), "node_modules/\n")

    def test_write_generated_content_requires_force_to_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / ".gitignore"
            output.write_text("old\n", "utf8")
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                with self.assertRaises(SystemExit):
                    gitig.write_generated_content(str(output), "new\n", False, False)
            self.assertIn("already exists", stderr.getvalue())
            self.assertEqual(output.read_text("utf8"), "old\n")

    def test_write_generated_content_force_overwrites(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / ".gitignore"
            output.write_text("old\n", "utf8")
            gitig.write_generated_content(str(output), "new\n", True, False)
            self.assertEqual(output.read_text("utf8"), "new\n")

    def test_write_generated_content_append_merges_and_dedupes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / ".gitignore"
            output.write_text("old\nshared\n", "utf8")
            gitig.write_generated_content(str(output), "shared\nnew\n", False, True)
            self.assertEqual(output.read_text("utf8"), "old\nshared\nnew\n")

    def test_spinner_writes_status_to_stderr_when_interactive(self) -> None:
        class FakeStream(io.StringIO):
            def isatty(self) -> bool:
                return True

        class FakeResponse:
            headers: dict[str, str] = {}
            status = 200

            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, exc_type, exc, tb) -> None:
                return None

            def read(self) -> bytes:
                return b"payload"

        stream = FakeStream()
        with (
            mock.patch.object(gitig_spinner.sys, "stderr", stream),
            mock.patch.object(gitig_core, "urlopen", return_value=FakeResponse()),
            mock.patch.object(gitig_spinner.Spinner, "START_DELAY_SECONDS", 0),
        ):
            payload = gitig.fetch_text("https://example.com/test", "Fetching example payload")
        self.assertEqual(payload, "payload")
        self.assertIn("Fetching example payload", stream.getvalue())
        self.assertIn("done Fetching example payload", stream.getvalue())

    def test_spinner_stays_quiet_when_not_interactive(self) -> None:
        class FakeStream(io.StringIO):
            def isatty(self) -> bool:
                return False

        class FakeResponse:
            headers: dict[str, str] = {}
            status = 200

            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, exc_type, exc, tb) -> None:
                return None

            def read(self) -> bytes:
                return b"payload"

        stream = FakeStream()
        with (
            mock.patch.object(gitig_spinner.sys, "stderr", stream),
            mock.patch.object(gitig_core, "urlopen", return_value=FakeResponse()),
            mock.patch.object(gitig_spinner.Spinner, "START_DELAY_SECONDS", 0),
        ):
            payload = gitig.fetch_text("https://example.com/test", "Fetching example payload")
        self.assertEqual(payload, "payload")
        self.assertEqual(stream.getvalue(), "")


class LicenseTests(unittest.TestCase):
    def test_parse_front_matter_extracts_metadata(self) -> None:
        metadata, body = gitig.parse_front_matter("---\ntitle: MIT License\nspdx-id: MIT\n---\nBody\n")
        self.assertEqual(metadata["title"], "MIT License")
        self.assertEqual(metadata["spdx-id"], "MIT")
        self.assertEqual(body, "Body\n")

    def test_apply_license_placeholders_only_defaults_year(self) -> None:
        rendered = gitig.apply_license_placeholders(
            "Copyright [year]\n[fullname]\n[project]\n[projecturl]\n",
            {"year": None, "fullname": None, "project": None, "project_url": None},
        )
        self.assertTrue(rendered.startswith(f"Copyright {time.gmtime().tm_year}\n"))
        self.assertIn("[fullname]\n", rendered)
        self.assertIn("[project]\n", rendered)
        self.assertIn("[projecturl]\n", rendered)

    def test_apply_license_placeholders_replaces_all_supported_fields(self) -> None:
        rendered = gitig.apply_license_placeholders(
            "[year] [yyyy] <year> [fullname] [name of copyright owner] [project] [projecturl] [project-url]",
            {
                "year": "2026",
                "fullname": "Jane Doe",
                "project": "gitig",
                "project_url": "https://example.com/gitig",
            },
        )
        self.assertEqual(
            rendered,
            "2026 2026 2026 Jane Doe Jane Doe gitig https://example.com/gitig https://example.com/gitig",
        )

    def test_resolve_license_invocation_defaults_to_list(self) -> None:
        self.assertEqual(gitig.resolve_license_invocation([]), ("list", []))


class DispatchTests(unittest.TestCase):
    def test_main_version_alias_prints_version(self) -> None:
        output = io.StringIO()
        with mock.patch.object(gitig.sys, "argv", ["gitig.py", "-v"]), contextlib.redirect_stdout(output):
            gitig.main()
        self.assertEqual(output.getvalue().strip(), gitig.get_version())

    def test_main_verison_typo_alias_prints_version(self) -> None:
        output = io.StringIO()
        with mock.patch.object(gitig.sys, "argv", ["gitig.py", "--verison"]), contextlib.redirect_stdout(output):
            gitig.main()
        self.assertEqual(output.getvalue().strip(), gitig.get_version())

    def test_print_help_reads_packaged_asset(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            gitig.print_help()
        self.assertIn("Usage:", output.getvalue())
        self.assertIn("gitig gh:Node -nc", output.getvalue())

    def test_cmd_completion_reads_packaged_asset(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            gitig.cmd_completion("bash")
        self.assertIn("_gitig_template_stub", output.getvalue())

    def test_main_bare_template_prints_to_stdout_by_default(self) -> None:
        captured: list[object] = []
        with mock.patch.object(gitig.sys, "argv", ["gitig.py", "gh:python"]), mock.patch.object(
            gitig_cli, "cmd_init", side_effect=lambda *args, **kwargs: captured.append((args, kwargs))
        ):
            gitig.main()
        self.assertEqual(len(captured), 1)
        self.assertTrue(captured[0][1]["force_stdout"])

    def test_main_bare_template_append_uses_write_path(self) -> None:
        captured: list[object] = []
        with mock.patch.object(gitig.sys, "argv", ["gitig.py", "gh:python", "-nac"]), mock.patch.object(
            gitig_cli, "cmd_init", side_effect=lambda *args, **kwargs: captured.append((args, kwargs))
        ):
            gitig.main()
        self.assertEqual(len(captured), 1)
        self.assertFalse(captured[0][1]["force_stdout"])
        self.assertTrue(captured[0][0][5])
        self.assertTrue(captured[0][0][7])

    def test_main_license_defaults_to_list(self) -> None:
        called: list[bool] = []
        with mock.patch.object(gitig.sys, "argv", ["gitig.py", "license"]), mock.patch.object(
            gitig_cli, "cmd_license_list", side_effect=lambda no_cache: called.append(no_cache)
        ):
            gitig.main()
        self.assertEqual(called, [False])

    def test_main_invalid_long_flag_prints_unrecognized_command(self) -> None:
        stderr = io.StringIO()
        with mock.patch.object(gitig.sys, "argv", ["gitig.py", "--wat"]), contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as exc:
                gitig.main()
        self.assertEqual(exc.exception.code, 1)
        self.assertEqual(stderr.getvalue().strip(), "unrecognized command")

    def test_main_invalid_short_flag_prints_unrecognized_command(self) -> None:
        stderr = io.StringIO()
        with mock.patch.object(gitig.sys, "argv", ["gitig.py", "-z"]), contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as exc:
                gitig.main()
        self.assertEqual(exc.exception.code, 1)
        self.assertEqual(stderr.getvalue().strip(), "unrecognized command")


if __name__ == "__main__":
    unittest.main()
