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
PREFIX = "v2/"
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


def source_path(release_path, image_class):
    marker = "/images/" + image_class + "/"
    if release_path.count(marker) != 1:
        raise RuntimeError(f"invalid class folder: {release_path}")
    return release_path.replace(marker, "/images/", 1)


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
    out.mkdir(parents=True, exist_ok=True)
    existing = {p.name for p in out.iterdir()}
    if any(not name.startswith("drone-detection-v2-images-") or not name.endswith(".zip") for name in existing):
        raise SystemExit(f"output contains unexpected files: {out}")
    if not existing and shutil.disk_usage(out).free < 7_000_000_000:
        raise SystemExit("less than 7 GB free; leaving current dataset untouched")
    rows = list(csv.DictReader((repo / "metadata/image_index.csv").open(newline="")))
    if len(rows) != 24245 or len({r["path"] for r in rows}) != len(rows) or len({r["sha256"] for r in rows}) != len(rows):
        raise RuntimeError("image index does not represent 24,245 distinct files")
    old_to_new = {source_path(r["path"], r["classes"]): r["path"] for r in rows}
    if len(old_to_new) != len(rows):
        raise RuntimeError("source image path collision")
    assets = []
    chunks = []
    current = []
    total = 0
    for row in rows:
        rel = pathlib.PurePosixPath(row["path"])
        if rel.is_absolute() or ".." in rel.parts or rel.parts[0] not in {"canonical", "augmented"}:
            raise RuntimeError(f"unsafe image path: {rel}")
        path = srcroot / source_path(row["path"], row["classes"])
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
        dest = out / f"drone-detection-v2-images-{number:02d}.zip"
        if dest.exists():
            with zipfile.ZipFile(dest) as z:
                expected = [PREFIX + row["path"] for row in chunk]
                if z.namelist() != expected:
                    raise RuntimeError(f"existing shard has wrong image paths: {dest}")
        else:
            with zipfile.ZipFile(dest, "w", allowZip64=True) as z:
                for row in chunk:
                    add_file(z, srcroot / source_path(row["path"], row["classes"]), row["path"])
        info = asset_info(dest, len(chunk))
        assets.append(info)
        print(f"built {info['name']}: {len(chunk)} images, {info['size_bytes']} bytes", flush=True)
    metadata_files = []
    for dirname in ("metadata", "by_class", "class_views"):
        metadata_files.extend((p, str(p.relative_to(repo))) for p in sorted((repo / dirname).rglob("*")) if p.is_file() and p.name != ".DS_Store")
    metadata_files.extend((repo / name, name) for name in ("README.md", "TRAINING_GUIDE.md", "scripts/verify_release.py"))
    stress_annotations = [str(p.relative_to(srcroot)) for p in sorted((srcroot / "augmented/test_stress").glob("*/annotations/instances.json"))]
    annotation_paths = ANNOTATIONS + stress_annotations
    metadata_files.extend((srcroot / name, name) for name in annotation_paths + OTHER_METADATA)
    dest = out / "drone-detection-v2-metadata.zip"
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as z:
        for path, rel in metadata_files:
            if rel in annotation_paths:
                data = json.loads(path.read_text())
                split_root = rel.split("/annotations/")[0]
                for image in data["images"]:
                    old = split_root + "/" + image["file_name"]
                    new = old_to_new.get(old)
                    if new is None:
                        raise RuntimeError(f"COCO image absent from release index: {old}")
                    image["file_name"] = new.removeprefix(split_root + "/")
                z.writestr(PREFIX + rel, json.dumps(data, separators=(",", ":")), compress_type=zipfile.ZIP_DEFLATED)
            elif rel == "augmented/provenance.csv":
                import io
                output = io.StringIO(newline="")
                with path.open(newline="") as f:
                    reader = csv.DictReader(f)
                    writer = csv.DictWriter(output, fieldnames=reader.fieldnames)
                    writer.writeheader()
                    for row in reader:
                        old = f"augmented/{row['output_split']}/images/{pathlib.PurePosixPath(row['file_name']).name}"
                        new = old_to_new.get(old)
                        if new is None:
                            raise RuntimeError(f"provenance image absent from release index: {old}")
                        row["file_name"] = new.split("/images/", 1)[1]
                        parent = f"canonical/{row['source_split']}/{row['parent_file']}"
                        if parent in old_to_new:
                            row["parent_file"] = old_to_new[parent].split(f"canonical/{row['source_split']}/", 1)[1]
                        writer.writerow(row)
                z.writestr(PREFIX + rel, output.getvalue(), compress_type=zipfile.ZIP_DEFLATED)
            else:
                add_file(z, path, rel)
    info = asset_info(dest, len(metadata_files))
    assets.append(info)
    print(f"built {info['name']}: {len(metadata_files)} files, {info['size_bytes']} bytes", flush=True)
    manifest = {
        "version": "drone-detection-v2.0-20261014",
        "unique_images": len(rows),
        "canonical_images": sum(r["view"] == "canonical" for r in rows),
        "augmented_images": sum(r["view"] == "augmented" for r in rows),
        "assets": assets,
    }
    (repo / "release_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("manifest written", flush=True)


if __name__ == "__main__":
    main()
