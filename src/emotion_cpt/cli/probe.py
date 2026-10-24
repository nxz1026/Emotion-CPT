"""契约指纹探针 —— 给上游 CI 用的机器可读输出。"""

from __future__ import annotations

import argparse

from emotion_cpt.db.probe import dump, fingerprint


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="契约指纹探针")
    parser.add_argument("--fingerprint-only", action="store_true", help="只输出指纹")
    args = parser.parse_args(argv)
    if args.fingerprint_only:
        print(fingerprint())
        return 0
    print(dump())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
