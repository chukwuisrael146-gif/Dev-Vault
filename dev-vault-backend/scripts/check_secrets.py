"""Fail if recognizable real credential shapes or private-key material enter Git-visible files."""

import re
import subprocess
from pathlib import Path

PATTERNS = [
    re.compile(rb"\bdv_(?:test|live)_[a-f0-9]{32}_[A-Za-z0-9_-]{43}\b"),
    re.compile(rb"\bdvs_[a-f0-9]{32}_[A-Za-z0-9_-]{43}\b"),
    re.compile(rb"\bwhsec_[A-Za-z0-9_-]{43}\b"),
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
]


def main():
    root = Path(__file__).resolve().parents[1]
    paths = (
        subprocess.check_output(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z", "."], cwd=root
        )
        .decode()
        .split("\0")
    )
    failures = []
    for relative in sorted(set(paths) - {""}):
        path = root / relative
        if not path.is_file():
            continue
        if path.name == ".env" or (path.name.startswith(".env.") and path.name != ".env.example"):
            failures.append(relative)
            continue
        if path.stat().st_size > 2_000_000:
            continue
        contents = path.read_bytes()
        if any(pattern.search(contents) for pattern in PATTERNS):
            failures.append(relative)
    if failures:
        print("Potential secret material found (values intentionally omitted):")
        for path in failures:
            print(path)
        return 1
    print("No recognizable credential/private-key material found in Git-visible backend files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
