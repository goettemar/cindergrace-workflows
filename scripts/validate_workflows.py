#!/usr/bin/env python3
"""Validate workflow bundles for structure, size, and hashes."""
import argparse
import hashlib
import sys
from pathlib import Path
from typing import Dict, Any, List

import yaml

MAX_SIZE_BYTES = 2 * 1024 * 1024  # 2 MB

REQUIRED_FILES = {
    "metadata.yaml",
    "workflow_api.json",
    "workflow_original.json",
}

OPTIONAL_FILES = {
    "README.md",
    "preview.png",
}

REQUIRED_META_FIELDS = {
    "name",
    "version",
    "author",
    "description",
    "tags",
    "min_comfyui_version",
    "compatible_cindergrace_versions",
    "required_models",
    "recommended_vram_gb",
    "contains_non_manager_nodes",
    "non_manager_nodes_info",
    "hashes",
}

REQUIRED_HASH_FIELDS = {"api_json", "original_json"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_metadata(path: Path) -> Dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("metadata.yaml must be a mapping")
    return data


def validate_bundle(bundle_dir: Path, errors: List[str]) -> None:
    files = {p.name for p in bundle_dir.iterdir() if p.is_file()}
    missing = REQUIRED_FILES - files
    if missing:
        errors.append(f"{bundle_dir}: missing files: {', '.join(sorted(missing))}")
        return

    models_files = [p.name for p in bundle_dir.iterdir() if p.is_file() and p.suffix == ".models"]
    if len(models_files) != 1:
        errors.append(f"{bundle_dir}: must contain exactly one .models file")
        return

    allowed = REQUIRED_FILES | OPTIONAL_FILES | set(models_files)
    unknown = sorted(files - allowed)
    if unknown:
        errors.append(f"{bundle_dir}: unknown files present: {', '.join(unknown)}")

    # Size check
    for name in REQUIRED_FILES | set(models_files):
        path = bundle_dir / name
        if path.stat().st_size > MAX_SIZE_BYTES:
            errors.append(f"{bundle_dir}: {name} exceeds 2 MB")

    meta_path = bundle_dir / "metadata.yaml"
    try:
        meta = load_metadata(meta_path)
    except Exception as exc:
        errors.append(f"{bundle_dir}: invalid metadata.yaml ({exc})")
        return

    missing_fields = REQUIRED_META_FIELDS - set(meta.keys())
    if missing_fields:
        errors.append(f"{bundle_dir}: metadata missing fields: {', '.join(sorted(missing_fields))}")
        return

    hashes = meta.get("hashes") or {}
    if not isinstance(hashes, dict):
        errors.append(f"{bundle_dir}: metadata hashes must be a mapping")
        return

    if REQUIRED_HASH_FIELDS - set(hashes.keys()):
        errors.append(f"{bundle_dir}: metadata hashes missing api_json/original_json")
        return

    api_hash = sha256_file(bundle_dir / "workflow_api.json")
    original_hash = sha256_file(bundle_dir / "workflow_original.json")
    if api_hash != hashes.get("api_json"):
        errors.append(f"{bundle_dir}: api_json hash mismatch")
    if original_hash != hashes.get("original_json"):
        errors.append(f"{bundle_dir}: original_json hash mismatch")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate workflow bundles")
    parser.add_argument("--root", default="workflows", help="Root workflows directory")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if not root.exists():
        print(f"ERROR: workflows root not found: {root}")
        return 1

    errors: List[str] = []
    bundles = [p for p in root.rglob("*") if p.is_dir() and (p / "metadata.yaml").exists()]
    if not bundles:
        print("WARNING: No workflow bundles found (metadata.yaml missing)")
        return 0

    for bundle in bundles:
        validate_bundle(bundle, errors)

    if errors:
        print("VALIDATION FAILED:")
        for err in errors:
            print(f"- {err}")
        return 1

    print(f"Validation OK: {len(bundles)} bundle(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
