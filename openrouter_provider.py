"""Bounded, optional OpenRouter transport with a hard paid daily budget."""

import json
import os
import stat
import threading
import time
import urllib.error
import urllib.request


KEY_FILENAME = "openrouter.key"
MODELS_URL = "https://openrouter.ai/api/v1/models"
CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
MAX_KEY_BYTES = 512
MAX_CATALOGUE_BYTES = 2 * 1024 * 1024
MAX_CHAT_RESPONSE_BYTES = 65536
MAX_MODELS = 128
REQUEST_TIMEOUT_SECONDS = 5.0
MODEL_COOLDOWN_SECONDS = 60.0
DAILY_PAID_BUDGET_USD = 1.0
MAX_PAID_RESERVATION_USD = 0.05
PRICING_FIELDS = frozenset((
    "prompt", "completion", "request", "image", "image_output",
    "audio", "audio_output", "web_search", "internal_reasoning",
    "input_audio_cache", "input_cache_read", "input_cache_write",
    "input_cache_write_1h"
))
CATALOGUE_URLS = frozenset((MODELS_URL, CHAT_URL))


class ProviderError(RuntimeError):
    pass


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, *arguments, **keywords):
        raise urllib.error.HTTPError(
            request.full_url, 310, "redirects are disabled", None, None
        )


def _default_opener(request, timeout):
    opener = urllib.request.build_opener(_NoRedirectHandler())
    return opener.open(request, timeout=timeout)


class OpenRouterProvider(object):
    """Uses bounded paid text models, then free models, never exceeding $1/day."""

    def __init__(self, directory=".", opener=None, time_source=None):
        self.directory = os.path.abspath(directory)
        self.opener = opener or _default_opener
        self.time_source = time_source or time.monotonic
        self.lock = threading.RLock()
        self.models = []
        self.paid_models = []
        self.cooldowns = {}
        self.next_index = 0
        self.status = "disabled_by_config"
        self.last_error = None
        self.paid_day = int(time.time() // 86400)
        self.paid_reserved = 0.0

    def _load_key(self):
        filename = os.path.join(self.directory, KEY_FILENAME)
        try:
            flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
            flags |= getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(filename, flags)
            metadata = os.fstat(descriptor)
            owner = getattr(os, "geteuid", lambda: metadata.st_uid)()
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != owner
                or metadata.st_mode & 0o077
            ):
                os.close(descriptor)
                self.status = "key_missing"
                return None
            with os.fdopen(descriptor, "rb") as handle:
                value = handle.read(MAX_KEY_BYTES + 1)
        except OSError:
            self.status = "key_missing"
            return None

        if len(value) == 0 or len(value) > MAX_KEY_BYTES:
            self.status = "key_missing"
            return None

        try:
            text = value.decode("ascii").strip()
        except UnicodeError:
            self.status = "key_missing"
            return None

        if not text or any(character.isspace() for character in text):
            self.status = "key_missing"
            return None

        return text

    @staticmethod
    def _is_zero_price(value):
        return isinstance(value, str) and value.strip() in ("0", "0.0", "0.00", "0.000000")

    @classmethod
    def is_text_model(cls, model):
        if not isinstance(model, dict):
            return False
        if not isinstance(model.get("id"), str) or not model["id"]:
            return False
        architecture = model.get("architecture")
        pricing = model.get("pricing")
        if not isinstance(architecture, dict) or not isinstance(pricing, dict):
            return False
        if tuple(architecture.get("input_modalities", ())) != ("text",):
            return False
        if tuple(architecture.get("output_modalities", ())) != ("text",):
            return False
        if (
            not isinstance(model.get("context_length"), int)
            or model["context_length"] < 512
        ):
            return False
        if not pricing or set(pricing) - PRICING_FIELDS:
            return False
        supported = model.get("supported_parameters")
        if not isinstance(supported, list):
            return False
        if not {
            "max_tokens", "temperature", "response_format"
        }.issubset(supported):
            return False
        return True

    @classmethod
    def is_free_text_model(cls, model):
        return cls.is_text_model(model) and all(
            cls._is_zero_price(value)
            for value in model["pricing"].values()
        )

    @staticmethod
    def _price(model, field):
        try:
            value = float(model["pricing"].get(field, "0"))
        except (TypeError, ValueError):
            return None
        if value < 0:
            return None
        return value

    def _reset_budget_if_needed(self):
        day = int(time.time() // 86400)
        if day != self.paid_day:
            self.paid_day = day
            self.paid_reserved = 0.0

    def _request_json(self, url, payload=None):
        if url not in CATALOGUE_URLS:
            raise ProviderError("catalogue_unavailable")
        key = self._load_key()
        if key is None:
            raise ProviderError(self.status)
        data = None if payload is None else json.dumps(payload, separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            headers={
                "Authorization": "Bearer " + key,
                "Accept": "application/json",
                "Content-Type": "application/json"
            }
        )
        try:
            response = self.opener(request, timeout=REQUEST_TIMEOUT_SECONDS)
            try:
                maximum = (
                    MAX_CATALOGUE_BYTES
                    if payload is None else MAX_CHAT_RESPONSE_BYTES
                )
                data = response.read(maximum + 1)
            finally:
                response.close()
        except urllib.error.HTTPError as error:
            if error.code == 429:
                self.status = "rate_limited"
            elif error.code == 402:
                self.status = "temporarily_exhausted"
            else:
                self.status = (
                    "catalogue_unavailable"
                    if payload is None else "circuit_open"
                )
            raise ProviderError(self.status)
        except (OSError, urllib.error.URLError):
            self.status = "catalogue_unavailable" if payload is None else "circuit_open"
            raise ProviderError(self.status)
        maximum = MAX_CATALOGUE_BYTES if payload is None else MAX_CHAT_RESPONSE_BYTES
        if len(data) > maximum:
            self.status = "catalogue_unavailable" if payload is None else "circuit_open"
            raise ProviderError(self.status)
        try:
            return json.loads(data.decode("utf-8"))
        except (UnicodeError, ValueError):
            self.status = "catalogue_unavailable" if payload is None else "circuit_open"
            raise ProviderError(self.status)

    def refresh_models(self):
        document = self._request_json(MODELS_URL)
        data = document.get("data") if isinstance(document, dict) else None
        models = [model for model in data or () if self.is_text_model(model)]
        free_models = [model for model in models if self.is_free_text_model(model)]
        paid_models = [model for model in models if model not in free_models and all(
            self._price(model, field) is not None
            for field in ("prompt", "completion", "request")
        ) and all(
            self._price(model, field) == 0.0
            for field in model["pricing"]
            if field not in ("prompt", "completion", "request")
        )]
        free_models.sort(key=lambda model: model["id"])
        paid_models.sort(key=lambda model: model["id"])
        with self.lock:
            self.models = free_models[:MAX_MODELS]
            self.paid_models = paid_models[:MAX_MODELS]
            self.next_index = 0
            self.status = "healthy" if (self.models or self.paid_models) else "no_free_models"
        return tuple(model["id"] for model in self.paid_models + self.models)

    def next_model(self):
        with self.lock:
            self._reset_budget_if_needed()
            now = self.time_source()
            candidates = self.paid_models + self.models
            if not candidates:
                self.status = "no_free_models"
                return None
            for unused in range(len(candidates)):
                model = candidates[self.next_index % len(candidates)]["id"]
                self.next_index += 1
                if (
                    model in tuple(item["id"] for item in self.paid_models)
                    and self.paid_reserved >= DAILY_PAID_BUDGET_USD
                ):
                    continue
                if self.cooldowns.get(model, 0.0) <= now:
                    return model
            self.status = "temporarily_exhausted"
            return None

    def clear_circuit(self):
        with self.lock:
            self.cooldowns.clear()
            if self.models or self.paid_models:
                self.status = "healthy"
            elif self.status in ("circuit_open", "temporarily_exhausted"):
                self.status = "no_free_models"

    def complete(self, messages, max_tokens=120):
        if not isinstance(messages, list) or not 1 <= len(messages) <= 8:
            raise ValueError("messages must be a bounded non-empty list")
        if isinstance(max_tokens, bool) or not isinstance(max_tokens, int):
            raise ValueError("max_tokens must be an integer")
        if not 1 <= max_tokens <= 64:
            raise ValueError("max_tokens is outside the bounded range")
        encoded_messages = json.dumps(
            messages, ensure_ascii=True, separators=(",", ":")
        ).encode("utf-8")
        if len(encoded_messages) > 8192:
            raise ValueError("messages are too large")
        for unused in range(min(2, len(self.paid_models) + len(self.models))):
            model = self.next_model()
            if model is None:
                return None
            model_data = next(item for item in self.paid_models + self.models if item["id"] == model)
            paid = model_data in self.paid_models
            reservation = 0.0
            if paid:
                prompt_price = self._price(model_data, "prompt")
                completion_price = self._price(model_data, "completion")
                request_price = self._price(model_data, "request")
                reservation = min(
                    MAX_PAID_RESERVATION_USD,
                    (len(encoded_messages) / 4.0) * prompt_price
                    + max_tokens * completion_price + request_price
                )
                with self.lock:
                    self._reset_budget_if_needed()
                    if self.paid_reserved + reservation > DAILY_PAID_BUDGET_USD:
                        self.cooldowns[model] = self.time_source() + MODEL_COOLDOWN_SECONDS
                        continue
                    self.paid_reserved += reservation
            payload = {
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": 0.4,
                "stream": False,
                "modalities": ["text"],
                "response_format": {"type": "json_object"},
                "tools": [],
                "provider": {
                    "allow_fallbacks": True,
                    "require_parameters": True,
                    "data_collection": "deny",
                    "max_price": {
                        "prompt": reservation if paid else 0,
                        "completion": reservation if paid else 0,
                        "request": reservation if paid else 0,
                        "image": 0
                    }
                }
            }
            try:
                document = self._request_json(CHAT_URL, payload)
                content = document["choices"][0]["message"]["content"]
                if not isinstance(content, str) or len(content) > 4096:
                    raise KeyError("invalid completion")
            except (KeyError, IndexError, TypeError, ProviderError):
                with self.lock:
                    self.cooldowns[model] = self.time_source() + MODEL_COOLDOWN_SECONDS
                    self.status = "circuit_open"
                continue
            with self.lock:
                self.status = "healthy"
                self.cooldowns.pop(model, None)
            return content
        with self.lock:
            self.status = "temporarily_exhausted"
        return None
