"""Isolated audio parsing worker. Parent enforces wall-clock and output limits."""

import json, sys
from .warp_analysis import analyze_file

if __name__ == "__main__":
    try:
        request = json.loads(sys.stdin.read(16384))
        print(json.dumps(analyze_file(**request), allow_nan=False))
    except Exception as error:
        print(json.dumps({"error": str(error)}))
        sys.exit(1)
