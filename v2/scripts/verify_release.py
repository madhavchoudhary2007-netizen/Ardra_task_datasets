#!/usr/bin/env python3
"""Verify extracted class-organized drone-detection-v2 images and index integrity."""
import csv
import hashlib
import pathlib
import sys
from collections import defaultdict


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: verify_release.py /path/to/v2")
    root = pathlib.Path(sys.argv[1]).resolve()
    index = root / "metadata" / "image_index.csv"
    if not index.is_file():
        raise SystemExit(f"missing {index}")
    seen_paths = set()
    seen_hashes = set()
    groups = defaultdict(set)
    count = 0
    for row in csv.DictReader(index.open(newline="")):
        rel = pathlib.PurePosixPath(row["path"])
        if rel.is_absolute() or ".." in rel.parts or not rel.parts or rel.parts[0] not in {"canonical", "augmented"}:
            raise SystemExit(f"unsafe image path: {rel}")
        if row["path"] in seen_paths or row["sha256"] in seen_hashes:
            raise SystemExit(f"duplicate path or image content: {rel}")
        seen_paths.add(row["path"])
        seen_hashes.add(row["sha256"])
        groups[row["leakage_group"]].add(row["partition"])
        image = root / rel
        if not image.is_file() or image.stat().st_size != int(row["size_bytes"]):
            raise SystemExit(f"missing or wrong-sized image: {image}")
        digest = hashlib.sha256()
        with image.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != row["sha256"]:
            raise SystemExit(f"SHA-256 mismatch: {image}")
        count += 1
    if count != 24245 or len(groups) != 1898 or any(len(parts) != 1 for parts in groups.values()):
        raise SystemExit(f"wrong image or source-group counts: {count} images, {len(groups)} groups")
    print(f"PASS: {count} unique verified images; {len(groups)} source groups; no split leakage")


if __name__ == "__main__":
    main()
