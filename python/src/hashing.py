"""Deterministic hashing: exact (SHA-256) and perceptual (pHash).

Both are pure, well-understood algorithms — no AI involved, per the
project's "AI only where it adds value" rule.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

from config import PHASH_SIZE

_CHUNK = 1024 * 1024


def sha256_of_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(_CHUNK)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def perceptual_hash_of_image(path: str | Path) -> Optional[str]:
    """Returns a hex string perceptual hash, or None if the file cannot be
    decoded as a raster image (e.g. SVG, corrupted file)."""
    try:
        import imagehash
        from PIL import Image
    except ImportError:
        return None

    try:
        with Image.open(path) as img:
            img = img.convert("RGB")
            phash = imagehash.phash(img, hash_size=PHASH_SIZE)
            return str(phash)
    except Exception:
        return None


def hamming_distance(hash_a: str, hash_b: str) -> Optional[int]:
    """Hamming distance between two hex perceptual hashes of equal length."""
    if not hash_a or not hash_b or len(hash_a) != len(hash_b):
        return None
    try:
        int_a = int(hash_a, 16)
        int_b = int(hash_b, 16)
    except ValueError:
        return None
    return bin(int_a ^ int_b).count("1")
