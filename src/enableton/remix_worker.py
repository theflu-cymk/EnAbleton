"""Isolated DSP entry point. JSON input/output; no Live access."""

import json
import sys
from .remix_assets import worker_job


def main():
    try:
        raw = sys.stdin.read(8_000_001)
        if len(raw) > 8_000_000:
            raise ValueError("Remix worker input too large")
        result = worker_job(json.loads(raw))
        print(json.dumps(result, allow_nan=False))
        return 0
    except Exception as error:
        print(json.dumps(dict(error=str(error))))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
