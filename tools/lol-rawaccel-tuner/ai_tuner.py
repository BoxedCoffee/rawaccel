import json
import os
import time
import urllib.request


class AzureOpenAIClient:
    def __init__(self, endpoint, api_key, deployment, api_version):
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key
        self.deployment = deployment
        self.api_version = api_version

    def chat(self, messages, temperature=0.2, max_tokens=600):
        url = (
            f"{self.endpoint}/openai/deployments/{self.deployment}/chat/completions"
            f"?api-version={self.api_version}"
        )
        body = {
            "messages": messages,
            "temperature": float(temperature),
            "max_tokens": int(max_tokens),
        }

        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("api-key", self.api_key)

        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))

        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise RuntimeError("no choices")

        msg = choices[0].get("message")
        if not isinstance(msg, dict):
            raise RuntimeError("missing message")

        content = msg.get("content")
        if not isinstance(content, str):
            raise RuntimeError("missing content")

        return content


def _env(name):
    v = os.environ.get(name)
    if v is None:
        return None
    v = v.strip()
    return v or None


def default_azure_config():
    return {
        "endpoint": _env("AZURE_OPENAI_ENDPOINT") or "",
        "api_key": _env("AZURE_OPENAI_API_KEY") or "",
        "deployment": _env("AZURE_OPENAI_DEPLOYMENT") or "",
        "api_version": _env("AZURE_OPENAI_API_VERSION") or "2024-02-15-preview",
    }


def build_ai_messages(state):
    system = (
        "You are an expert mouse-aim tuning assistant. "
        "Given the user's trial metrics, propose the next RawAccel synchronous parameters to try. "
        "You must output STRICT JSON only (no markdown, no prose)."
    )

    user = {
        "task": "propose_next_candidate",
        "timestamp": int(time.time()),
        "mode": state.get("mode"),
        "bounds": state.get("bounds"),
        "fixed": state.get("fixed"),
        "history": state.get("history"),
        "best": state.get("best"),
        "objective": state.get("objective"),
        "limits": state.get("limits"),
    }

    schema = {
        "stop": "boolean",
        "confidence": "number 0..1",
        "candidate": {
            "syncSpeed": "number",
            "motivity": "number",
            "gamma": "number",
            "smooth": "number",
        },
        "reason": "short string",
    }

    return [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": json.dumps(
                {
                    "input": user,
                    "output_schema": schema,
                },
                indent=2,
            ),
        },
    ]


def parse_ai_response(text):
    try:
        obj = json.loads(text)
    except Exception:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        obj = json.loads(text[start : end + 1])

    if not isinstance(obj, dict):
        raise ValueError("response is not an object")

    cand = obj.get("candidate")
    if not isinstance(cand, dict):
        raise ValueError("missing candidate")

    out = {
        "stop": bool(obj.get("stop", False)),
        "confidence": float(obj.get("confidence", 0.0)),
        "reason": str(obj.get("reason", ""))[:300],
        "candidate": {
            "syncSpeed": float(cand.get("syncSpeed")),
            "motivity": float(cand.get("motivity")),
            "gamma": float(cand.get("gamma")),
            "smooth": float(cand.get("smooth")),
        },
    }

    return out


def clamp_candidate(candidate, bounds):
    out = {}
    for k, v in candidate.items():
        if k not in bounds:
            continue
        lo, hi = bounds[k]
        x = float(v)
        if x < float(lo):
            x = float(lo)
        if x > float(hi):
            x = float(hi)
        out[k] = x

    out["syncSpeed"] = max(1e-6, float(out.get("syncSpeed", 5.0)))
    out["gamma"] = max(1e-6, float(out.get("gamma", 1.0)))
    out["motivity"] = max(1.000001, float(out.get("motivity", 1.5)))
    out["smooth"] = min(1.0, max(0.0, float(out.get("smooth", 0.5))))

    return out
