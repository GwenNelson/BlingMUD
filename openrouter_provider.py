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
QUERY_LOG_FILENAME = "openrouter_queries.jsonl"
BUDGET_FILENAME = "openrouter_budget.json"
MAX_QUERY_LOG_BYTES = 20 * 1024 * 1024
MAX_AUDIT_RESPONSE_BYTES = (MAX_CHAT_RESPONSE_BYTES + 1) * 6 + 4096
PREFERRED_PAID_MODELS = (
    "meta-llama/llama-3.3-70b-instruct",
    "qwen/qwen3-30b-a3b-instruct-2507",
    "openai/gpt-3.5-turbo"
)
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
        self.audit_lock = threading.Lock()
        self.audit_reserved_bytes = 0
        self.models = []
        self.paid_models = []
        self.cooldowns = {}
        self.next_index = 0
        self.status = "disabled_by_config"
        self.last_error = None
        self.paid_day = int(time.time() // 86400)
        self.paid_reserved = 0.0
        self._load_budget()

    def _load_budget(self):
        path = os.path.join(self.directory, BUDGET_FILENAME)
        try:
            with open(path, "r") as handle:
                document = json.load(handle)
            if (
                isinstance(document, dict)
                and document.get("day") == self.paid_day
                and isinstance(document.get("reserved_usd"), (int, float))
                and not isinstance(document.get("reserved_usd"), bool)
                and document["reserved_usd"] >= 0
            ):
                self.paid_reserved = min(
                    float(document["reserved_usd"]),
                    DAILY_PAID_BUDGET_USD
                )
        except (OSError, TypeError, ValueError):
            pass

    def _save_budget(self):
        path = os.path.join(self.directory, BUDGET_FILENAME)
        encoded = json.dumps({
            "day": self.paid_day,
            "reserved_usd": round(self.paid_reserved, 9)
        }, separators=(",", ":")).encode("ascii")
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        flags |= getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags, 0o600)
        try:
            os.fchmod(descriptor, 0o600)
            os.write(descriptor, encoded)
        finally:
            os.close(descriptor)

    def _audit_log(
        self, event, value, secret=None, reserve_bytes=0, release_bytes=0
    ):
        try:
            document = {
                "time": time.time(),
                "event": event,
                "value": value
            }
            encoded = json.dumps(
                document, ensure_ascii=True, separators=(",", ":")
            )
            if secret:
                encoded = encoded.replace(secret, "[REDACTED]")
            encoded = (encoded + "\n").encode("utf-8")
            path = os.path.join(self.directory, QUERY_LOG_FILENAME)
            flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
            flags |= getattr(os, "O_CLOEXEC", 0)
            flags |= getattr(os, "O_NOFOLLOW", 0)
            with self.audit_lock:
                self.audit_reserved_bytes = max(
                    0, self.audit_reserved_bytes - release_bytes
                )
                descriptor = os.open(path, flags, 0o600)
                try:
                    os.fchmod(descriptor, 0o600)
                    metadata = os.fstat(descriptor)
                    if (
                        metadata.st_size + self.audit_reserved_bytes
                        + len(encoded) + reserve_bytes
                        > MAX_QUERY_LOG_BYTES
                    ):
                        return False
                    written = 0
                    while written < len(encoded):
                        count = os.write(descriptor, encoded[written:])
                        if count <= 0:
                            raise OSError("short audit write")
                        written += count
                    self.audit_reserved_bytes += reserve_bytes
                    return True
                finally:
                    os.close(descriptor)
        except (OSError, TypeError, ValueError, OverflowError):
            return False

    def _release_audit_reservation(self, amount):
        with self.audit_lock:
            self.audit_reserved_bytes = max(
                0, self.audit_reserved_bytes - amount
            )

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
        if not {"max_tokens", "temperature"}.issubset(supported):
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
            self._save_budget()

    def _request_json(self, url, payload=None):
        if url not in CATALOGUE_URLS:
            raise ProviderError("catalogue_unavailable")
        key = self._load_key()
        if key is None:
            raise ProviderError(self.status)
        data = None if payload is None else json.dumps(payload, separators=(",", ":")).encode("utf-8")
        audit_reservation = MAX_AUDIT_RESPONSE_BYTES
        if not self._audit_log(
            "request",
            {"url": url, "payload": payload},
            secret=key,
            reserve_bytes=audit_reservation
        ):
            self.status = "audit_unavailable"
            raise ProviderError(self.status)
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
            try:
                error_body = error.read(MAX_CHAT_RESPONSE_BYTES + 1).decode(
                    "utf-8", "replace"
                )
            except Exception:
                error_body = ""
            audit_ok = self._audit_log(
                "response",
                {"url": url, "status": error.code, "body": error_body},
                secret=key,
                release_bytes=audit_reservation
            )
            if not audit_ok:
                self.status = "audit_unavailable"
            elif error.code == 429:
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
            audit_ok = self._audit_log(
                "response",
                {"url": url, "status": "transport_error", "body": ""},
                secret=key,
                release_bytes=audit_reservation
            )
            self.status = (
                "catalogue_unavailable" if payload is None else "circuit_open"
            ) if audit_ok else "audit_unavailable"
            raise ProviderError(self.status)
        except Exception:
            self._release_audit_reservation(audit_reservation)
            raise
        maximum = MAX_CATALOGUE_BYTES if payload is None else MAX_CHAT_RESPONSE_BYTES
        response_body = data.decode("utf-8", "replace")
        audit_ok = self._audit_log(
            "response",
            {
                "url": url,
                "status": 200,
                "body": (
                    response_body
                    if payload is not None
                    else json.dumps({"catalogue_bytes": len(data)})
                )
            },
            secret=key,
            release_bytes=audit_reservation
        )
        if not audit_ok:
            self.status = "audit_unavailable"
            raise ProviderError(self.status)
        if len(data) > maximum:
            self.status = "catalogue_unavailable" if payload is None else "circuit_open"
            raise ProviderError(self.status)
        try:
            return json.loads(response_body)
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
        preference = {
            identifier: index
            for index, identifier in enumerate(PREFERRED_PAID_MODELS)
        }
        paid_models.sort(key=lambda model: (
            preference.get(model["id"], len(preference)),
            (self._price(model, "prompt") or 0.0)
            + (self._price(model, "completion") or 0.0),
            model["id"]
        ))
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
        if not 1 <= max_tokens <= 192:
            raise ValueError("max_tokens is outside the bounded range")
        encoded_messages = json.dumps(
            messages, ensure_ascii=True, separators=(",", ":")
        ).encode("utf-8")
        if len(encoded_messages) > 16384:
            raise ValueError("messages are too large")
        for unused in range(min(4, len(self.paid_models) + len(self.models))):
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
                # The payload is ASCII JSON. One byte per prompt token is a
                # conservative tokenizer-independent ceiling; the former
                # four-bytes-per-token estimate was typical, not a hard cap.
                reservation = (
                    len(encoded_messages) * prompt_price
                    + max_tokens * completion_price + request_price
                )
                if reservation > MAX_PAID_RESERVATION_USD:
                    with self.lock:
                        self.cooldowns[model] = (
                            self.time_source() + MODEL_COOLDOWN_SECONDS
                        )
                    continue
                with self.lock:
                    self._reset_budget_if_needed()
                    if self.paid_reserved + reservation > DAILY_PAID_BUDGET_USD:
                        self.cooldowns[model] = self.time_source() + MODEL_COOLDOWN_SECONDS
                        continue
                    self.paid_reserved += reservation
                    self._save_budget()
            payload = {
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": 0.4,
                "stream": False,
                "provider": {
                    "allow_fallbacks": True,
                    "data_collection": "deny",
                    "max_price": {
                        "prompt": prompt_price * 1000000 if paid else 0,
                        "completion": completion_price * 1000000 if paid else 0,
                        "request": request_price if paid else 0,
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
                if paid:
                    usage = document.get("usage", {})
                    actual = usage.get("cost") if isinstance(usage, dict) else None
                    if (
                        isinstance(actual, (int, float))
                        and not isinstance(actual, bool)
                        and 0 <= actual <= MAX_PAID_RESERVATION_USD
                    ):
                        self.paid_reserved = min(
                            DAILY_PAID_BUDGET_USD,
                            max(
                                0.0,
                                self.paid_reserved - reservation
                                + float(actual)
                            )
                        )
                        self._save_budget()
            return content
        with self.lock:
            self.status = "temporarily_exhausted"
        return None
