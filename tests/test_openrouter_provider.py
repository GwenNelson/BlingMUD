import io
import json
import os
import tempfile
import unittest

from openrouter_provider import OpenRouterProvider


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
        with open(os.path.join(self.directory.name, "openrouter.key"), "w") as handle:
            handle.write("test-key")
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
        return {"id": identifier, "context_length": 4096, "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]}, "pricing": pricing}

    def test_catalogue_accepts_only_known_zero_price_text_models_and_rotates(self):
        provider = OpenRouterProvider(self.directory.name, opener=self._opener)
        self.assertEqual(provider.refresh_models(), ("free/b",))
        self.assertEqual(provider.next_model(), "free/b")
        self.assertEqual(provider.next_model(), "free/b")
        self.assertEqual(provider.status, "healthy")
        self.assertNotIn(b"test-key", self.requests[0][0].data or b"")

    def test_missing_key_never_calls_transport(self):
        os.unlink(os.path.join(self.directory.name, "openrouter.key"))
        provider = OpenRouterProvider(self.directory.name, opener=self._opener)
        with self.assertRaises(Exception):
            provider.refresh_models()
        self.assertEqual(self.requests, [])
        self.assertEqual(provider.status, "key_missing")


if __name__ == "__main__":
    unittest.main()
