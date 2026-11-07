"""Isolated PCM repair scan; parent bounds execution time and output."""

import json
import sys

from .audio_scan import scan_pcm

if __name__ == "__main__":
    try:
        print(json.dumps(scan_pcm(**json.loads(sys.stdin.read(16384))), allow_nan=False))
    except Exception as error:
        print(json.dumps({"error": str(error)}))
        sys.exit(1)
