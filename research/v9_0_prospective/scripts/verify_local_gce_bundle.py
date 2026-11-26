#!/usr/bin/env python3
from __future__ import annotations
import hashlib
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[3]
V9_DIR = PACKAGE_ROOT / "research" / "v9_0_prospective"
EXPECTED_POOL_SHA256 = "128ff78bb6beb1640fa51897ab97dbb9d07dc56de276973d05a48dda524b53d3"
EXPECTED_POOL_BYTES = 75875
manifest = V9_DIR / "MANIFEST_SHA256.txt"
entries = 0
for line in manifest.read_text(encoding="utf-8").splitlines():
    if not line.strip():
        continue
    digest, relative = line.split("  ", 1)
    path = V9_DIR / relative
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != digest:
        raise SystemExit(f"BLOCKED: manifest check failed for {relative}")
    entries += 1
pool = PACKAGE_ROOT / "items_pool_v1.json"
pool_data = pool.read_bytes()
if len(pool_data) != EXPECTED_POOL_BYTES or hashlib.sha256(pool_data).hexdigest() != EXPECTED_POOL_SHA256:
    raise SystemExit("BLOCKED: the item pool size or SHA-256 does not match")
print(f"Verified {entries} manifest files and the 260-item pool ({len(pool_data)} bytes).")
