from __future__ import annotations

import copy
import hashlib
import http.client
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
from urllib.parse import urlsplit

from forgejo_release_mirror.mirror import API, synchronize


class HTTPTest(unittest.TestCase):
    def setUp(self) -> None:
        self.release = None
        self.assets = []
        self.requests = []
        self.content = b"fixture package bytes"
        state = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def respond(self, status, value):
                body = value if isinstance(value, bytes) else json.dumps(value).encode()
                self.send_response(status)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def record(self):
                path = urlsplit(self.path).path
                token = (
                    "source-fixture"
                    if path.startswith(("/api/v1/", "/source/"))
                    else "target-fixture"
                )
                state.requests.append(
                    (self.command, path, self.headers.get("Authorization"))
                )
                if self.headers.get("Authorization") != f"Bearer {token}":
                    self.respond(401, {})
                    return None
                return path

            def do_GET(self):
                path = self.record()
                if path is None:
                    return
                responses = {
                    "/api/v1/repos/source/project/releases": [
                        {
                            "id": 1,
                            "tag_name": "v1.0.0",
                            "name": "Version one",
                            "body": "Release notes",
                            "draft": False,
                            "prerelease": False,
                            "published_at": "2026-11-17T00:00:00Z",
                        }
                    ],
                    "/api/v1/repos/source/project/tags/v1.0.0": {
                        "commit": {"sha": "a" * 40}
                    },
                    "/api/v1/repos/source/project/releases/1/assets": [
                        {"name": "package.whl", "size": len(state.content)}
                    ],
                    "/source/project/releases/download/v1.0.0/package.whl": state.content,
                    "/repos/public/mirror/git/ref/tags/v1.0.0": {
                        "object": {"type": "commit", "sha": "a" * 40}
                    },
                    "/repos/public/mirror/releases": [state.release]
                    if state.release
                    else [],
                    "/repos/public/mirror/releases/2/assets": state.assets,
                }
                if path == "/repos/public/mirror/releases/tags/v1.0.0":
                    self.respond(200 if state.release else 404, state.release or {})
                elif path in responses:
                    self.respond(200, responses[path])
                else:
                    self.respond(404, {})

            def do_POST(self):
                path = self.record()
                if path is None:
                    return
                body = self.rfile.read(int(self.headers["Content-Length"]))
                if path == "/repos/public/mirror/releases":
                    state.release = json.loads(body) | {"id": 2}
                    self.respond(201, state.release)
                elif path == "/repos/public/mirror/releases/2/assets":
                    if body != state.content:
                        self.respond(400, {})
                        return
                    asset = {
                        "id": 3,
                        "name": "package.whl",
                        "state": "uploaded",
                        "digest": "sha256:" + hashlib.sha256(body).hexdigest(),
                    }
                    state.assets.append(asset)
                    self.respond(201, asset)
                else:
                    self.respond(404, {})

            def do_PATCH(self):
                path = self.record()
                if path != "/repos/public/mirror/releases/2" or state.release is None:
                    if path is not None:
                        self.respond(404, {})
                    return
                state.release.update(
                    json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                )
                self.respond(200, state.release)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.origin = f"http://127.0.0.1:{self.server.server_port}"
        self.forgejo = API(self.origin, "source-fixture", "/api/v1")
        self.github = API(self.origin, "target-fixture")

    def stop_server(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def run_sync(self, dry_run: bool = False):
        def connection(host, timeout):
            self.assertEqual(host, "uploads.github.com")
            return http.client.HTTPConnection(
                "127.0.0.1", self.server.server_port, timeout=timeout
            )

        with patch(
            "forgejo_release_mirror.mirror.http.client.HTTPSConnection",
            side_effect=connection,
        ):
            return synchronize(
                self.forgejo,
                self.github,
                "source/project",
                "1.0.0",
                destination_repository="public/mirror",
                dry_run=dry_run,
            )

    def test_real_http_cycle_uploads_before_publishing_then_repeats_without_writes(
        self,
    ) -> None:
        result = self.run_sync()
        self.assertEqual(result[0]["uploaded_assets"], 1)
        self.assertFalse(self.release["draft"])
        self.assertEqual(
            [method for method, _, _ in self.requests if method != "GET"],
            ["POST", "POST", "PATCH"],
        )
        previous = copy.deepcopy(self.release)
        self.requests.clear()
        result = self.run_sync()
        self.assertEqual(result[0]["uploaded_assets"], 0)
        self.assertFalse(result[0]["updated"])
        self.assertEqual(self.release, previous)
        self.assertTrue(all(method == "GET" for method, _, _ in self.requests))

    def test_real_http_preview_has_no_writes_or_asset_downloads(self) -> None:
        result = self.run_sync(dry_run=True)
        self.assertEqual(
            result, [{"tag": "v1.0.0", "action": "create", "assets": ["package.whl"]}]
        )
        self.assertIsNone(self.release)
        self.assertEqual(self.assets, [])
        self.assertTrue(all(method == "GET" for method, _, _ in self.requests))
        self.assertFalse(any("/download/" in path for _, path, _ in self.requests))
