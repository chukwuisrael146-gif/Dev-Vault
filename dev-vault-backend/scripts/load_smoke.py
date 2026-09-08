"""Bounded read-only loopback health timing, not an authorization SLO benchmark."""

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, build_opener


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--requests", type=int, default=50)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    url = urlsplit(args.base_url)
    if (
        url.scheme != "http"
        or url.hostname not in {"localhost", "127.0.0.1", "::1"}
        or url.username
        or url.password
        or url.path not in {"", "/"}
        or url.query
        or url.fragment
        or not 1 <= args.requests <= 1000
        or not 1 <= args.workers <= 16
    ):
        parser.error("Use loopback HTTP, 1..1000 requests and 1..16 workers.")

    def probe(_):
        started = time.perf_counter()
        try:
            with build_opener(ProxyHandler({})).open(
                args.base_url.rstrip("/") + "/api/v1/health/live/", timeout=3
            ) as response:
                success = response.status == 200
        except OSError:
            success = False
        return success, (time.perf_counter() - started) * 1000

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(probe, range(args.requests)))
    times = sorted(item[1] for item in results)
    failures = sum(not item[0] for item in results)
    print(
        json.dumps(
            {
                "requests": len(results),
                "failures": failures,
                "p50_ms": round(times[int((len(times) - 1) * 0.50)], 2),
                "p95_ms": round(times[int((len(times) - 1) * 0.95)], 2),
                "note": "Liveness only, not a verification or production SLO benchmark.",
            }
        )
    )
    raise SystemExit(int(failures > 0))


if __name__ == "__main__":
    main()
