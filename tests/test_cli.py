from __future__ import annotations

import contextlib
import io
import json
import os
import unittest
from unittest.mock import patch

from forgejo_release_mirror.cli import main
from forgejo_release_mirror.mirror import synchronize
from tests.test_mirror import COMMIT, Forgejo, GitHub


class RepositoryTest(unittest.TestCase):
    def test_source_and_destination_paths_stay_separate(self) -> None:
        source, destination = Forgejo(), GitHub()
        with (
            patch.object(source, "json", wraps=source.json) as source_json,
            patch.object(source, "pages", wraps=source.pages) as source_pages,
            patch.object(source, "download", wraps=source.download) as download,
            patch.object(destination, "json", wraps=destination.json) as target_json,
            patch.object(destination, "pages", wraps=destination.pages) as target_pages,
            patch.object(destination, "upload", wraps=destination.upload) as upload,
        ):
            result = synchronize(
                source,
                destination,
                "source/project",
                "0.13.0",
                destination_repository="public/mirror",
            )
            self.assertEqual(result[0]["uploaded_assets"], 2)
            for call in [*source_json.call_args_list, *source_pages.call_args_list]:
                self.assertTrue(call.args[0].startswith("/repos/source/project/"))
            for call in download.call_args_list:
                self.assertTrue(call.args[0].startswith("/source/project/"))
            for call in [*target_json.call_args_list, *target_pages.call_args_list]:
                self.assertTrue(call.args[0].startswith("/repos/public/mirror/"))
            self.assertEqual(upload.call_args.args[0], "public/mirror")

    def test_dry_run_validates_tags_without_writes_or_downloads(self) -> None:
        source, destination = Forgejo(), GitHub()
        for existing in (False, True):
            with self.subTest(existing=existing):
                if existing:
                    synchronize(source, destination, "source/project", "0.13.0")
                    destination.writes.clear()
                with patch.object(source, "download") as download:
                    result = synchronize(
                        source, destination, "source/project", "0.13.0", dry_run=True
                    )
                self.assertEqual(
                    result,
                    [
                        {
                            "tag": "v0.13.0",
                            "action": "reconcile" if existing else "create",
                            "assets": ["package.whl", "SHA256SUMS"],
                        }
                    ],
                )
                self.assertEqual(destination.writes, [])
                download.assert_not_called()
        destination.commit = "b" * len(COMMIT)
        with self.assertRaisesRegex(RuntimeError, "tag differs"):
            synchronize(source, destination, "source/project", "0.13.0", dry_run=True)

    def test_invalid_destination_fails_before_network_access(self) -> None:
        source, destination = Forgejo(), GitHub()
        for name in (
            "",
            "../repo",
            "owner/..",
            "owner/repo/extra",
            "owner/repo?token=x",
        ):
            with (
                self.subTest(name=name),
                patch.object(source, "pages") as pages,
                self.assertRaises(ValueError),
            ):
                synchronize(
                    source,
                    destination,
                    "owner/repo",
                    "0.13.0",
                    destination_repository=name,
                )
            pages.assert_not_called()


class CLITest(unittest.TestCase):
    arguments = [
        "--forgejo-origin",
        "http://forgejo.test",
        "--source-repository",
        "source/project",
        "--destination-repository",
        "public/mirror",
        "--minimum-version",
        "0.13.0",
    ]

    def test_json_output_and_repository_arguments(self) -> None:
        output = io.StringIO()
        source, destination = Forgejo(), GitHub()
        with (
            patch.dict(
                os.environ, {"FORGEJO_READ_TOKEN": "source", "GITHUB_TOKEN": "target"}
            ),
            patch("forgejo_release_mirror.cli.API", side_effect=[source, destination]),
            contextlib.redirect_stdout(output),
        ):
            self.assertEqual(main([*self.arguments, "--dry-run"]), 0)
        result = json.loads(output.getvalue())
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["status"], "ok")
        self.assertEqual(destination.writes, [])

    def test_missing_and_malformed_tokens_fail_without_leaking_them(self) -> None:
        for value in (None, "", "secret token", "secret\nvalue"):
            with self.subTest(value=value):
                output, errors = io.StringIO(), io.StringIO()
                environment = {"GITHUB_TOKEN": "destination-secret"}
                if value is not None:
                    environment["FORGEJO_READ_TOKEN"] = value
                with (
                    patch.dict(os.environ, environment, clear=True),
                    patch("forgejo_release_mirror.cli.synchronize") as run,
                    contextlib.redirect_stdout(output),
                    contextlib.redirect_stderr(errors),
                ):
                    self.assertEqual(main(self.arguments), 1)
                run.assert_not_called()
                self.assertEqual(output.getvalue(), "")
                self.assertEqual(json.loads(errors.getvalue())["status"], "failed")
                self.assertNotIn("secret", errors.getvalue())

    def test_transport_failure_has_nonzero_status_and_json_error(self) -> None:
        errors = io.StringIO()
        with (
            patch.dict(
                os.environ, {"FORGEJO_READ_TOKEN": "source", "GITHUB_TOKEN": "target"}
            ),
            patch(
                "forgejo_release_mirror.cli.synchronize", side_effect=OSError("offline")
            ),
            contextlib.redirect_stderr(errors),
        ):
            self.assertEqual(main(self.arguments), 1)
        self.assertEqual(
            json.loads(errors.getvalue()), {"status": "failed", "error": "offline"}
        )
