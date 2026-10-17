"""The only door to the model. Every call: fixed model, temperature 1.0,
top_p 0.95, reasoning disabled, X-Item-Id header. A per-item call counter
enforces the budget locally so we can never exceed it."""
from __future__ import annotations

import json
import os
import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

import urllib.error
import urllib.request
import socket

MODEL = "ibm-granite/granite-4.2-8b"
TEMPERATURE = 1.0
TOP_P = 0.95


def _load_env() -> None:
    for p in (Path.cwd() / ".env", Path(__file__).resolve().parents[2] / ".env"):
        if p.exists():
            for line in p.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
            break


class BudgetExceeded(RuntimeError):
    pass


class GraniteClient:
    def __init__(self, log_path: Optional[str] = None, max_retries: int = 6):
        _load_env()
        self.base = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
        self.key = os.environ.get("OPENROUTER_API_KEY")
        if not self.key:
            raise RuntimeError("OPENROUTER_API_KEY missing (put it in .env)")
        model = MODEL  # fixed by the brief; deliberately not overridable
        if model != MODEL:
            raise RuntimeError(f"refusing to use model {model!r}; only {MODEL} is allowed")
        self.calls: Dict[str, int] = defaultdict(int)
        self.caps: Dict[str, int] = {}
        self.usage = defaultdict(int)
        self.lock = threading.Lock()
        self.max_retries = max_retries
        self.log_path = log_path

    def set_cap(self, item_id: str, cap: int) -> None:
        self.caps[item_id] = cap

    def remaining(self, item_id: str) -> int:
        return self.caps.get(item_id, 1) - self.calls[item_id]

    def chat(self, item_id: str, messages: List[dict], max_tokens: int = 2000) -> str:
        """One logical call. Every HTTP attempt that could reach the counting
        proxy is charged to the item's budget, so retries can never push an
        item over its cap; if the cap is hit we raise and the caller falls
        back to whatever it already has."""
        body = {
            "model": MODEL,
            "messages": messages,
            "temperature": TEMPERATURE,
            "top_p": TOP_P,
            "max_tokens": max_tokens,
            "reasoning": {"enabled": False},
        }
        headers = {"Authorization": f"Bearer {self.key}", "X-Item-Id": item_id,
                   "Content-Type": "application/json"}
        last = None
        for attempt in range(self.max_retries):
            with self.lock:
                if self.calls[item_id] >= self.caps.get(item_id, 1):
                    raise BudgetExceeded(f"{item_id}: {last}")
            with self.lock:
                self.calls[item_id] += 1
            status, raw = self._post(body, headers)
            if status == -1:  # connection refused / DNS: never reached the endpoint, refund
                with self.lock:
                    self.calls[item_id] -= 1
                last = raw
                time.sleep(min(30, 2 ** attempt))
                continue
            if status == 200:
                try:
                    j = json.loads(raw)
                except ValueError:
                    j = {}
                if j.get("choices"):
                    text = j["choices"][0]["message"].get("content") or ""
                    u = j.get("usage") or {}
                    with self.lock:
                        for k in ("prompt_tokens", "completion_tokens"):
                            self.usage[k] += int(u.get(k) or 0)
                        if u.get("cost") is not None:
                            self.usage["cost_micro_usd"] += int(float(u["cost"]) * 1e6)
                    self._log(item_id, messages, text)
                    return text
                last = f"no choices: {str(j)[:200]}"
            else:
                last = f"HTTP {status}: {raw[:200]}"
            time.sleep(min(30, 2 ** attempt))
        raise RuntimeError(f"model call failed for {item_id}: {last}")

    def _post(self, body: dict, headers: dict):
        req = urllib.request.Request(f"{self.base}/chat/completions",
                                     data=json.dumps(body).encode(), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace")
        except urllib.error.URLError as e:
            if isinstance(e.reason, (ConnectionRefusedError, socket.gaierror)):
                return -1, repr(e)
            return 0, repr(e)
        except (TimeoutError, socket.timeout, ConnectionError) as e:
            return 0, repr(e)

    def _log(self, item_id: str, messages: List[dict], text: str) -> None:
        if not self.log_path:
            return
        with self.lock, open(self.log_path, "a") as f:
            f.write(json.dumps({"item": item_id, "user": messages[-1]["content"][-400:],
                                "reply": text}) + "\n")
