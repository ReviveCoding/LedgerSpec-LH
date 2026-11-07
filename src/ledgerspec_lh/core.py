"""Deterministic host primitives; no model or evaluator dependencies."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


class Blocked(ValueError):
    def __init__(self, code, detail=""):
        self.code = code
        super().__init__(f"{code}: {detail}")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def timestamp(value):
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise Blocked("INVALID_TIME", "timezone required")
    return dt


def minor(value):
    if type(value) is not int or abs(value) > 9_000_000_000_000_000:
        raise Blocked("INVALID_MONEY", "bounded integer minor units required")
    return value


class ArtifactStore:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, value):
        data = canonical(value)
        key = hashlib.sha256(data).hexdigest()
        path = self.root / (key + ".json")
        try:
            with path.open("xb") as stream:
                stream.write(data)
                stream.flush()
                import os
                os.fsync(stream.fileno())
        except FileExistsError:
            if path.read_bytes() != data:
                raise Blocked("ARTIFACT_CONFLICT")
        return key

    def get(self, key):
        if len(key) != 64 or any(c not in "0123456789abcdef" for c in key):
            raise Blocked("INVALID_ARTIFACT_ID")
        data = (self.root / (key + ".json")).read_bytes()
        if hashlib.sha256(data).hexdigest() != key:
            raise Blocked("ARTIFACT_CORRUPTION")
        return json.loads(data)
