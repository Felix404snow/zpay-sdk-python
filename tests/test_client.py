import json
import math
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

from zpay import ZPay, ZPayError


class Fixture:
    def __init__(self, status=200, body=None, headers=None, error=None):
        self.calls = []
        self.status, self.body, self.headers, self.error = status, body if body is not None else {"status": "pending"}, headers or {}, error

    def __call__(self, method, url, headers, payload, timeout):
        self.calls.append((method, url, headers, payload))
        if self.error:
            raise self.error
        raw = self.body if isinstance(self.body, bytes) else json.dumps(self.body).encode()
        return self.status, self.headers, raw


class ClientTests(unittest.TestCase):
    def client(self, fixture):
        return ZPay("fixture-id", "fixture-secret", transport=fixture)

    def test_auth_query_and_precise_amounts(self):
        wire = Fixture()
        client = self.client(wire)
        client.payments.create({"amount": 19.9, "payerName": "Cliente", "idempotencyKey": "order-123"})
        self.assertEqual(json.loads(wire.calls[0][3])["amount"], 19.9)
        self.assertEqual(wire.calls[0][2]["client-secret"], "fixture-secret")
        client.crypto.withdraw({"requestId": "ltc-order-123", "amount": .12345678, "address": "ltc1q..."})
        self.assertEqual(json.loads(wire.calls[1][3])["amount"], .12345678)
        client.donations.list({"tag": "Loja & café", "hour": 0, "from": None})
        query = parse_qs(urlsplit(wire.calls[-1][1]).query)
        self.assertEqual(query["tag"], ["Loja & café"])
        self.assertEqual(query["hour"], ["0"])
        self.assertNotIn("from", query)

    def test_keys_required_before_dispatch_and_never_changed(self):
        wire = Fixture()
        client = self.client(wire)
        with self.assertRaises(ValueError):
            client.withdrawals.create({"amount": 10})
        with self.assertRaises(ValueError):
            client.crypto.swap({"amount": 10, "requestId": "short"})
        self.assertEqual(len(wire.calls), 0)
        data = {"amount": 10, "idempotencyKey": "withdraw-123"}
        client.withdrawals.create(data)
        client.withdrawals.create(data)
        self.assertEqual(wire.calls[0][3], wire.calls[1][3])

    def test_failure_has_no_retry_and_redacts(self):
        wire = Fixture(429, {"error": "fixture-secret", "code": "RATE_LIMIT", "nested": ["fixture-id"]}, {"Retry-After": "60"})
        with self.assertRaises(ZPayError) as result:
            self.client(wire).withdrawals.create({"amount": 10, "idempotencyKey": "order-1"})
        error = result.exception
        self.assertEqual(error.status, 429)
        self.assertEqual(error.code, "RATE_LIMIT")
        self.assertEqual(error.retry_after, "60")
        self.assertTrue(error.outcome_unknown)
        self.assertNotIn("fixture-secret", str(error))
        self.assertNotIn("fixture-id", str(error.details))
        self.assertEqual(len(wire.calls), 1)

    def test_timeout_and_malformed_response_are_uncertain(self):
        for wire in [Fixture(error=TimeoutError()), Fixture(body=b"<html>Challenge</html>"), Fixture(body=b"null"), Fixture(body=b"[]")]:
            with self.assertRaises(ZPayError) as result:
                self.client(wire).payments.create({"amount": 10, "payerName": "Cliente", "idempotencyKey": "order-1"})
            self.assertTrue(result.exception.outcome_unknown)
            self.assertEqual(len(wire.calls), 1)

    def test_202_and_validation(self):
        result = self.client(Fixture(202)).withdrawals.create({"amount": 10, "idempotencyKey": "order-1"})
        self.assertEqual(result["status"], "pending")
        for url in ["http://example.test", "https://user:pass@example.test", "https://example.test?secret=yes", "https://example.test#x"]:
            with self.assertRaises(ValueError):
                ZPay("id", "secret", base_url=url)
        for timeout in [0, -1, math.inf, math.nan]:
            with self.assertRaises(ValueError):
                ZPay("id", "secret", timeout=timeout)
        with self.assertRaises(ValueError):
            self.client(Fixture()).payments.get("..")

    def test_actual_http_redirect_cannot_forward_credentials(self):
        hits = []
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                hits.append(self.path)
                self.send_response(302)
                self.send_header("Location", "/steal")
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error":"redirect"}')
            def log_message(self, *_):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            client = ZPay("id", "secret", base_url=f"http://127.0.0.1:{server.server_port}/api/v1")
            with self.assertRaises(ZPayError) as result:
                client.account.fees()
            self.assertEqual(result.exception.status, 302)
            self.assertEqual(hits, ["/api/v1/fees"])
        finally:
            server.shutdown()
            server.server_close()
            worker.join()

    def test_every_resource_route_matches_manifest(self):
        manifest_path = Path(__file__).parents[1] / "operations.json"
        if not manifest_path.exists():
            manifest_path = Path(__file__).parents[2] / "operations.json"
        manifest = json.loads(manifest_path.read_text())
        import re
        snake = lambda name: re.sub(r"[A-Z]", lambda m: "_" + m[0].lower(), name)
        wire = Fixture()
        client = self.client(wire)
        for group, methods in manifest.items():
            for name, spec in methods.items():
                verb, route, kind, *key = spec
                data = {"amount": 12.34, "idempotencyKey": "order-123", "requestId": "crypto-order-123"}
                args = (["id/a?x=1"] if kind.startswith("id") else [])
                args += [data] if kind in ("body", "idBody") else [{"page": 2}] if kind in ("query", "idQuery") else ["@loja"] if kind == "to" else []
                getattr(getattr(client, snake(group)), snake(name))(*args)
                request = wire.calls[-1]
                self.assertEqual(request[0], verb)
                self.assertEqual(urlsplit(request[1]).path, "/api/v1" + route.replace("{id}", "id%2Fa%3Fx%3D1"))


if __name__ == "__main__":
    unittest.main()
