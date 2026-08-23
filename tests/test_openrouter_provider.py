import io
import json
import os
import stat
import tempfile
import time
import unittest

from openrouter_provider import (
    DAILY_PAID_BUDGET_USD,
    MAX_QUERY_LOG_BYTES,
    OpenRouterProvider
)


class FakeResponse(object):
    def __init__(self, document):
        self.data = json.dumps(document).encode("utf-8")

    def read(self, maximum):
        return self.data

    def close(self):
        pass


class OpenRouterProviderTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=".test-tmp")
        key_path = os.path.join(self.directory.name, "openrouter.key")
        with open(key_path, "w") as handle:
            handle.write("test-key")
        os.chmod(key_path, stat.S_IRUSR | stat.S_IWUSR)
        self.requests = []

    def tearDown(self):
        self.directory.cleanup()

    def _opener(self, request, timeout):
        self.requests.append((request, timeout))
        return FakeResponse({"data": [
            self._model("free/b", "0"),
            self._model("paid/a", "0.01"),
            self._model("unknown/c", "0", extra=True)
        ]})

    def _model(self, identifier, price, extra=False):
        pricing = {"prompt": price, "completion": price, "request": "0"}
        if extra:
            pricing["future_charge"] = "0"
        return {
            "id": identifier,
            "context_length": 4096,
            "architecture": {
                "input_modalities": ["text"],
                "output_modalities": ["text"]
            },
            "supported_parameters": [
                "max_tokens", "temperature", "response_format"
            ],
            "pricing": pricing
        }

    def test_catalogue_accepts_only_known_zero_price_text_models_and_rotates(self):
        provider = OpenRouterProvider(self.directory.name, opener=self._opener)
        self.assertEqual(provider.refresh_models(), ("paid/a", "free/b"))
        self.assertEqual(provider.next_model(), "paid/a")
        self.assertEqual(provider.next_model(), "free/b")
        self.assertEqual(provider.status, "healthy")
        self.assertNotIn(b"test-key", self.requests[0][0].data or b"")

    def test_paid_budget_is_bounded_and_free_models_remain_available(self):
        provider = OpenRouterProvider(self.directory.name, opener=self._opener)
        provider.refresh_models()
        provider.paid_reserved = 1.0
        self.assertEqual(provider.next_model(), "free/b")

    def test_paid_prompt_reservation_uses_strict_ascii_byte_ceiling(self):
        requests = []
        paid = self._model("paid/dense", "0.000001")
        free = self._model("free/fallback", "0")

        def opener(request, timeout):
            requests.append(request)
            if request.full_url.endswith("/models"):
                return FakeResponse({"data": [paid, free]})
            return FakeResponse({
                "choices": [{"message": {"content": '{"choice":0}'}}],
                "usage": {"cost": 0.0}
            })

        provider = OpenRouterProvider(self.directory.name, opener=opener)
        provider.refresh_models()
        provider.paid_reserved = DAILY_PAID_BUDGET_USD - 0.0001

        self.assertEqual(
            provider.complete(
                [{"role": "user", "content": "x" * 100}],
                max_tokens=1
            ),
            '{"choice":0}'
        )
        payload = json.loads(requests[-1].data.decode("utf-8"))
        self.assertEqual(payload["model"], "free/fallback")
        self.assertLessEqual(
            provider.paid_reserved,
            DAILY_PAID_BUDGET_USD
        )

    def test_over_limit_persisted_budget_fails_closed_at_daily_cap(self):
        budget_path = os.path.join(
            self.directory.name, "openrouter_budget.json"
        )
        with open(budget_path, "w") as handle:
            json.dump({
                "day": int(time.time() // 86400),
                "reserved_usd": DAILY_PAID_BUDGET_USD + 10.0
            }, handle)
        os.chmod(budget_path, 0o600)

        provider = OpenRouterProvider(
            self.directory.name,
            opener=self._opener
        )

        self.assertEqual(
            provider.paid_reserved,
            DAILY_PAID_BUDGET_USD
        )

    def test_preferred_paid_dialogue_model_is_selected_first(self):
        preferred = self._model(
            "meta-llama/llama-3.3-70b-instruct", "0.000001"
        )
        ordinary = self._model("paid/a", "0.0000001")
        def opener(request, timeout):
            return FakeResponse({"data": [ordinary, preferred]})
        provider = OpenRouterProvider(self.directory.name, opener=opener)
        provider.refresh_models()
        self.assertEqual(
            provider.next_model(), "meta-llama/llama-3.3-70b-instruct"
        )

    def test_insecure_key_is_disabled(self):
        key_path = os.path.join(self.directory.name, "openrouter.key")
        os.chmod(key_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP)
        provider = OpenRouterProvider(self.directory.name, opener=self._opener)
        with self.assertRaises(Exception):
            provider.refresh_models()
        self.assertEqual(provider.status, "key_missing")

    def test_catalogue_requires_exact_text_modalities_and_request_support(self):
        model = self._model("free/a", "0")
        self.assertTrue(OpenRouterProvider.is_free_text_model(model))
        model["architecture"]["input_modalities"] = ["text", "image"]
        self.assertFalse(OpenRouterProvider.is_free_text_model(model))
        model = self._model("free/a", "0")
        model["supported_parameters"] = ["max_tokens"]
        self.assertFalse(OpenRouterProvider.is_free_text_model(model))

    def test_oversized_catalogue_is_rejected(self):
        class OversizedResponse(FakeResponse):
            def __init__(self):
                self.data = b"{" + (b"x" * (2 * 1024 * 1024))

        def oversized_opener(request, timeout):
            return OversizedResponse()

        provider = OpenRouterProvider(
            self.directory.name, opener=oversized_opener
        )
        with self.assertRaises(Exception):
            provider.refresh_models()
        self.assertEqual(provider.status, "catalogue_unavailable")

    def test_missing_key_never_calls_transport(self):
        os.unlink(os.path.join(self.directory.name, "openrouter.key"))
        provider = OpenRouterProvider(self.directory.name, opener=self._opener)
        with self.assertRaises(Exception):
            provider.refresh_models()
        self.assertEqual(self.requests, [])
        self.assertEqual(provider.status, "key_missing")

    def test_raw_audit_log_excludes_key(self):
        path = os.path.join(self.directory.name, "openrouter_queries.jsonl")
        with open(path, "w") as handle:
            handle.write("")
        os.chmod(path, 0o644)
        provider = OpenRouterProvider(self.directory.name, opener=self._opener)
        provider.refresh_models()
        with open(path, "r") as handle:
            logged = handle.read()
        self.assertIn('"event":"request"', logged)
        self.assertIn('"event":"response"', logged)
        self.assertNotIn("test-key", logged)
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)

    def test_full_audit_log_prevents_unlogged_remote_request(self):
        path = os.path.join(self.directory.name, "openrouter_queries.jsonl")
        with open(path, "wb") as handle:
            handle.truncate(MAX_QUERY_LOG_BYTES)
        os.chmod(path, 0o600)
        provider = OpenRouterProvider(self.directory.name, opener=self._opener)
        with self.assertRaises(Exception):
            provider.refresh_models()
        self.assertEqual(provider.status, "audit_unavailable")
        self.assertEqual(self.requests, [])

    def test_paid_request_uses_per_million_max_price_and_persists_budget(self):
        requests = []
        paid = self._model("paid/working", "0.000001")
        def opener(request, timeout):
            requests.append(request)
            if request.full_url.endswith("/models"):
                return FakeResponse({"data": [paid]})
            return FakeResponse({
                "choices": [{"message": {"content": '{"choice":0}'}}],
                "usage": {"cost": 0.0001}
            })
        provider = OpenRouterProvider(self.directory.name, opener=opener)
        provider.refresh_models()
        self.assertEqual(provider.complete(
            [{"role": "user", "content": "choose"}], max_tokens=8
        ), '{"choice":0}')
        payload = json.loads(requests[-1].data.decode("utf-8"))
        self.assertEqual(payload["provider"]["max_price"]["prompt"], 1.0)
        budget_path = os.path.join(
            self.directory.name, "openrouter_budget.json"
        )
        self.assertEqual(stat.S_IMODE(os.stat(budget_path).st_mode), 0o600)
        restored = OpenRouterProvider(self.directory.name, opener=opener)
        self.assertAlmostEqual(restored.paid_reserved, 0.0001)


if __name__ == "__main__":
    unittest.main()
