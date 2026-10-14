#!/usr/bin/env python3
"""Build duplicate-free ZIP assets and a checksum manifest for GitHub Releases."""
import csv
import hashlib
import json
import pathlib
import shutil
import sys
import zipfile

LIMIT = 1_600_000_000  # Safe margin below GitHub's 2 GiB per-asset limit.
PREFIX = "drone_dataset_final/"
ANNOTATIONS = [
    "canonical/train/annotations/instances.json",
    "canonical/val_original/annotations/instances.json",
    "canonical/test_original/annotations/instances.json",
    "augmented/train/annotations/instances.json",
    "augmented/val_drone/annotations/instances.json",
    "augmented/test_drone/annotations/instances.json",
]
OTHER_METADATA = [
    "augmented/provenance.csv",
    "augmented/augmentation_summary.json",
    "configs/approved_hard_negatives_v3.csv",
    "qa/full_source_review/STATUS.md",
    "qa/full_source_review/manifest.json",
    "qa/full_source_review/fullres_adjudication.csv",
    "qa/full_source_review/review_queue.csv",
    "qa/full_source_review/missing_instance_exceptions.csv",
]


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def add_file(z, src, name):
    if not src.is_file():
        raise RuntimeError(f"missing {src}")
    z.write(src, PREFIX + name, compress_type=zipfile.ZIP_STORED)


def asset_info(path, file_count):
    with zipfile.ZipFile(path) as z:
        bad = z.testzip()
        if bad:
            raise RuntimeError(f"ZIP CRC failed: {path}: {bad}")
        if len(z.namelist()) != file_count:
            raise RuntimeError(f"wrong entry count: {path}")
    size = path.stat().st_size
    if size >= 2 * 1024**3:
        raise RuntimeError(f"asset is too large for GitHub: {path}")
    return {"name": path.name, "size_bytes": size, "sha256": digest(path), "entries": file_count}


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: build_release.py DATASET_ROOT OUTPUT_DIRECTORY")
    srcroot = pathlib.Path(sys.argv[1]).resolve()
    out = pathlib.Path(sys.argv[2]).resolve()
    repo = pathlib.Path(__file__).resolve().parents[1]
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"output must be empty: {out}")
    out.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(out).free < 7_000_000_000:
        raise SystemExit("less than 7 GB free; leaving current dataset untouched")
    rows = list(csv.DictReader((repo / "metadata/image_index.csv").open(newline="")))
    if len(rows) != 24245 or len({r["path"] for r in rows}) != len(rows) or len({r["sha256"] for r in rows}) != len(rows):
        raise RuntimeError("image index does not represent 24,245 distinct files")
    assets = []
    chunks = []
    current = []
    total = 0
    for row in rows:
        rel = pathlib.PurePosixPath(row["path"])
        if rel.is_absolute() or ".." in rel.parts or rel.parts[0] not in {"canonical", "augmented"}:
            raise RuntimeError(f"unsafe image path: {rel}")
        path = srcroot / rel
        size = int(row["size_bytes"])
        if not path.is_file() or path.stat().st_size != size:
            raise RuntimeError(f"missing or wrong-sized image: {path}")
        if current and total + size > LIMIT:
            chunks.append(current)
            current, total = [], 0
        current.append(row)
        total += size
    if current:
        chunks.append(current)
    for number, chunk in enumerate(chunks, 1):
        dest = out / f"drone-detection-v1-images-{number:02d}.zip"
        with zipfile.ZipFile(dest, "w", allowZip64=True) as z:
            for row in chunk:
                add_file(z, srcroot / row["path"], row["path"])
        info = asset_info(dest, len(chunk))
        assets.append(info)
        print(f"built {info['name']}: {len(chunk)} images, {info['size_bytes']} bytes", flush=True)
    metadata_files = []
    for dirname in ("metadata", "by_class", "class_views"):
        metadata_files.extend((p, str(p.relative_to(repo))) for p in sorted((repo / dirname).rglob("*")) if p.is_file() and p.name != ".DS_Store")
    metadata_files.extend((repo / name, name) for name in ("README.md", "TRAINING_GUIDE.md", "scripts/verify_release.py"))
    metadata_files.extend((srcroot / name, name) for name in ANNOTATIONS + OTHER_METADATA)
    dest = out / "drone-detection-v1-metadata.zip"
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as z:
        for path, rel in metadata_files:
            add_file(z, path, rel)
    info = asset_info(dest, len(metadata_files))
    assets.append(info)
    print(f"built {info['name']}: {len(metadata_files)} files, {info['size_bytes']} bytes", flush=True)
    manifest = {
        "version": "drone-detection-v1.0-20261014",
        "unique_images": len(rows),
        "canonical_images": sum(r["view"] == "canonical" for r in rows),
        "augmented_images": sum(r["view"] == "augmented" for r in rows),
        "assets": assets,
    }
    (repo / "release_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("manifest written", flush=True)


if __name__ == "__main__":
    main()
