"""Stage 2: deterministic metadata extraction.

One "inspect()" call per discovered file. Never raises — any failure is
captured as inspection_ok=False + inspection_error, so one corrupted or
unusual file never takes down the whole batch (see docs/architecture-decision.md §9).
"""
from __future__ import annotations

import json
import mimetypes
import re
import subprocess
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from config import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS, DOCUMENT_EXTENSIONS, SOURCE_ONLY_EXTENSIONS
from hashing import sha256_of_file, perceptual_hash_of_image

mimetypes.init()


@dataclass
class AssetMetadata:
    filename: str
    relpath: str
    extension: str
    asset_type: str            # image | video | document | source_unsupported | unsupported
    mime: Optional[str] = None
    size_bytes: int = 0
    width: Optional[int] = None
    height: Optional[int] = None
    duration_seconds: Optional[float] = None
    codec: Optional[str] = None
    container: Optional[str] = None
    sha256: Optional[str] = None
    perceptual_hash: Optional[str] = None
    modified_at: Optional[str] = None
    in_source_folder: bool = False
    inspection_ok: bool = True
    inspection_error: Optional[str] = None


def _asset_type_for_extension(ext: str) -> str:
    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext in VIDEO_EXTENSIONS:
        return "video"
    if ext in DOCUMENT_EXTENSIONS:
        return "document"
    if ext in SOURCE_ONLY_EXTENSIONS:
        return "source_unsupported"
    return "unsupported"


def _svg_dimensions(path: Path) -> tuple[Optional[int], Optional[int]]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")[:4000]
        w_match = re.search(r'width="([\d.]+)', text)
        h_match = re.search(r'height="([\d.]+)', text)
        if w_match and h_match:
            return int(float(w_match.group(1))), int(float(h_match.group(1)))
        vb_match = re.search(r'viewBox="[\d.\-]+\s+[\d.\-]+\s+([\d.]+)\s+([\d.]+)"', text)
        if vb_match:
            return int(float(vb_match.group(1))), int(float(vb_match.group(2)))
    except Exception:
        pass
    return None, None


def _image_dimensions(path: Path, ext: str) -> tuple[Optional[int], Optional[int]]:
    if ext == ".svg":
        return _svg_dimensions(path)
    from PIL import Image
    with Image.open(path) as img:
        img.verify()  # raises if the file is truncated/corrupt
    with Image.open(path) as img:  # reopen: verify() leaves the file unusable for further ops
        return img.size


def _pdf_dimensions(path: Path) -> tuple[Optional[int], Optional[int]]:
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        if reader.pages:
            box = reader.pages[0].mediabox
            return int(box.width), int(box.height)
    except Exception:
        pass
    return None, None


def _video_probe(path: Path) -> dict:
    """Runs ffprobe and returns duration/codec/container/dimensions.
    This is exactly the kind of operation the architecture decision calls
    out as impractical inside n8n natively -> delegated to Python/ffmpeg."""
    cmd = [
        "ffprobe", "-v", "error",
        "-print_format", "json",
        "-show_format", "-show_streams",
        str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {proc.stderr.strip()[:300]}")
    data = json.loads(proc.stdout)
    video_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    fmt = data.get("format", {})
    width = video_stream.get("width") if video_stream else None
    height = video_stream.get("height") if video_stream else None
    codec = video_stream.get("codec_name") if video_stream else None
    duration = fmt.get("duration") or (video_stream.get("duration") if video_stream else None)
    container = fmt.get("format_name")
    return {
        "width": width,
        "height": height,
        "codec": codec,
        "duration_seconds": float(duration) if duration else None,
        "container": container,
    }


def inspect_file(absolute_path: Path, relpath: str, extension: str, in_source_folder: bool) -> AssetMetadata:
    stat = absolute_path.stat()
    meta = AssetMetadata(
        filename=absolute_path.name,
        relpath=relpath,
        extension=extension.lstrip("."),
        asset_type=_asset_type_for_extension(extension),
        mime=mimetypes.guess_type(absolute_path.name)[0],
        size_bytes=stat.st_size,
        modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        in_source_folder=in_source_folder,
    )

    try:
        meta.sha256 = sha256_of_file(absolute_path)

        if meta.asset_type == "image":
            meta.width, meta.height = _image_dimensions(absolute_path, extension)
            if extension != ".svg":
                meta.perceptual_hash = perceptual_hash_of_image(absolute_path)

        elif meta.asset_type == "video":
            probe = _video_probe(absolute_path)
            meta.width = probe["width"]
            meta.height = probe["height"]
            meta.codec = probe["codec"]
            meta.duration_seconds = probe["duration_seconds"]
            meta.container = probe["container"]

        elif meta.asset_type == "document":
            meta.width, meta.height = _pdf_dimensions(absolute_path)

        elif meta.asset_type == "source_unsupported":
            # Deliberately not deep-parsed (see architecture-decision.md §"discovery").
            # We still have sha256/size/mtime above, which is all delivery
            # packaging actually needs for these formats.
            meta.inspection_error = "proprietary_format_metadata_limited"

        else:
            meta.inspection_ok = False
            meta.inspection_error = "unsupported_format"

    except Exception as exc:  # noqa: BLE001 - intentional: one bad file must not stop the batch
        meta.inspection_ok = False
        meta.inspection_error = f"{type(exc).__name__}: {exc}"[:500]

    return meta


def metadata_to_dict(meta: AssetMetadata) -> dict:
    return asdict(meta)
