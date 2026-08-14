#!/usr/bin/env python3
"""Offline verifier for a Codex-generated image handed to RedBeacon.

This is a technical-spike tool, not the production host-import protocol. It
proves that a concrete local file returned by Codex can be decoded, sanitized
with RedBeacon's real image boundary, and compared with a reference image when
the host performed image-to-image editing.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import stat
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CLI_SRC = ROOT / "cli" / "src"
if str(CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CLI_SRC))

from PIL import Image, ImageChops, ImageOps, ImageStat, UnidentifiedImageError  # noqa: E402

from redbeacon.services.image_sanitize import (  # noqa: E402
    ImageSanitizationError,
    _png_chunk_types,
    save_sanitized_generated_image,
)


MAX_INPUT_BYTES = 64 * 1024 * 1024
SUPPORTED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


class VerificationError(ValueError):
    """The handoff cannot be accepted as a safe local image asset."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _regular_image_file(raw: str | Path, *, label: str) -> Path:
    path = Path(raw).expanduser()
    try:
        info = path.lstat()
    except OSError as exc:
        raise VerificationError(f"{label} does not exist: {path}") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise VerificationError(f"{label} must be a regular non-symlink file")
    if info.st_size <= 0 or info.st_size > MAX_INPUT_BYTES:
        raise VerificationError(f"{label} size is outside the accepted range")
    resolved = path.resolve(strict=True)
    if resolved.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise VerificationError(f"{label} must be JPG, PNG, or WebP")
    return resolved


def _output_directory(raw: str | Path) -> Path:
    path = Path(raw).expanduser()
    if path.exists() and path.is_symlink():
        raise VerificationError("sanitized output directory cannot be a symlink")
    path.mkdir(parents=True, exist_ok=True)
    resolved = path.resolve(strict=True)
    if not resolved.is_dir():
        raise VerificationError("sanitized output path is not a directory")
    return resolved


def _image_summary(data: bytes) -> dict:
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            return {
                "format": image.format or "",
                "width": image.width,
                "height": image.height,
                "mode": image.mode,
                "info_keys": sorted(str(key) for key in image.info),
                "exif_entries": len(image.getexif()),
            }
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise VerificationError("input is not a readable image") from exc


def _reference_comparison(reference_data: bytes, generated_data: bytes) -> dict:
    try:
        with Image.open(io.BytesIO(reference_data)) as reference_source:
            reference = ImageOps.exif_transpose(reference_source).convert("RGB")
        with Image.open(io.BytesIO(generated_data)) as generated_source:
            generated = ImageOps.exif_transpose(generated_source).convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise VerificationError("reference comparison could not decode both images") from exc

    same_dimensions = reference.size == generated.size
    result = {
        "same_dimensions": same_dimensions,
        "reference_width": reference.width,
        "reference_height": reference.height,
        "generated_width": generated.width,
        "generated_height": generated.height,
        "reference_sha256": _sha256(reference_data),
        "generated_sha256": _sha256(generated_data),
    }
    if not same_dimensions:
        result.update({"changed_pixel_ratio": None, "mean_abs_channel_delta": None})
        return result

    difference = ImageChops.difference(reference, generated)
    changed_mask = ImageChops.lighter(
        ImageChops.lighter(difference.getchannel("R"), difference.getchannel("G")),
        difference.getchannel("B"),
    )
    changed = reference.width * reference.height - changed_mask.histogram()[0]
    result.update({
        "changed_pixel_ratio": round(changed / max(1, reference.width * reference.height), 6),
        "mean_abs_channel_delta": [round(value, 3) for value in ImageStat.Stat(difference).mean],
    })
    return result


def verify_handoff(
    generated_path: str | Path,
    sanitized_dir: str | Path,
    *,
    reference_path: str | Path | None = None,
    require_same_dimensions: bool = False,
    require_reference_change: bool = False,
) -> dict:
    generated = _regular_image_file(generated_path, label="generated image")
    output_dir = _output_directory(sanitized_dir)
    generated_data = generated.read_bytes()
    input_summary = _image_summary(generated_data)

    try:
        sanitized_path = Path(
            save_sanitized_generated_image(generated_data, str(output_dir))
        ).resolve(strict=True)
    except ImageSanitizationError as exc:
        raise VerificationError(f"RedBeacon sanitizer rejected the image: {exc}") from exc

    sanitized_data = sanitized_path.read_bytes()
    sanitized_summary = _image_summary(sanitized_data)
    chunk_types = [chunk.decode("ascii", "replace") for chunk in _png_chunk_types(sanitized_data)]
    ancillary_chunks = [chunk for chunk in chunk_types if chunk and ord(chunk[0]) & 0x20]
    if ancillary_chunks or sanitized_summary["info_keys"] or sanitized_summary["exif_entries"]:
        raise VerificationError("sanitized output still contains metadata")
    if (input_summary["width"], input_summary["height"], input_summary["mode"]) != (
        sanitized_summary["width"],
        sanitized_summary["height"],
        sanitized_summary["mode"],
    ):
        raise VerificationError("sanitization changed dimensions or color mode")

    comparison = None
    if reference_path is not None:
        reference = _regular_image_file(reference_path, label="reference image")
        comparison = _reference_comparison(reference.read_bytes(), generated_data)
        if require_same_dimensions and not comparison["same_dimensions"]:
            raise VerificationError("edited image dimensions differ from the reference")
        if require_reference_change and not (comparison["changed_pixel_ratio"] or 0):
            raise VerificationError("edited image pixels are unchanged from the reference")

    return {
        "schema": "redbeacon-codex-image-handoff-spike/v1",
        "ok": True,
        "input": {
            "path": str(generated),
            "bytes": len(generated_data),
            "sha256": _sha256(generated_data),
            **input_summary,
        },
        "sanitized": {
            "path": str(sanitized_path),
            "bytes": len(sanitized_data),
            "sha256": _sha256(sanitized_data),
            "chunk_types": chunk_types,
            **sanitized_summary,
        },
        "reference_comparison": comparison,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify one Codex image file with RedBeacon's real sanitizer."
    )
    parser.add_argument("--generated", required=True, type=Path)
    parser.add_argument("--sanitized-dir", required=True, type=Path)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--require-same-dimensions", action="store_true")
    parser.add_argument("--require-reference-change", action="store_true")
    args = parser.parse_args()
    try:
        result = verify_handoff(
            args.generated,
            args.sanitized_dir,
            reference_path=args.reference,
            require_same_dimensions=args.require_same_dimensions,
            require_reference_change=args.require_reference_change,
        )
    except VerificationError as exc:
        raise SystemExit(f"verification failed: {exc}") from exc
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
