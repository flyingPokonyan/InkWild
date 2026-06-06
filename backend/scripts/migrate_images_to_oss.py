"""One-off migration: move local /static/images/* assets to OSS and rewrite DB URLs.

Background: image generation was implemented to support OSS (OSSImageStorage) but
IMAGE_STORAGE_BACKEND was left at "local", so every generated cover/hero/avatar
landed in backend/static/images/ and the DB stored relative "/static/images/..."
paths. This migrates the *referenced* assets to the already-configured OSS bucket
and rewrites every DB reference (plain text columns AND json/jsonb blobs).

Strategy (uniform prefix mapping):
    local  "/static/images/<key>"
    oss    "<oss_public_prefix>/<key>"   (== OSSImageStorage._public_url(<key>))
So the rewrite is a single prefix replace "/static/images/" -> "<oss_public_prefix>"
applied to every column that contains the marker.

Safety:
  * Default DRY-RUN. Nothing is uploaded or written without --apply.
  * Auto-discovers every text/json/jsonb column in the public schema that actually
    contains "/static/images/" — nothing hardcoded, nothing missed.
  * Before any DB write it uploads all referenced assets, then fetches ONE uploaded
    object over its public URL and asserts HTTP 200 (proves bucket is reachable +
    public-read). Aborts the whole migration otherwise.
  * Refuses to apply if any referenced asset file is missing locally (would create a
    dangling OSS link) — reports them instead.
  * Local files are NOT deleted. Re-runnable / idempotent (OSS put overwrites; rows
    already rewritten to http no longer match the marker).

Run (inside backend container):
    python scripts/migrate_images_to_oss.py            # dry-run report
    python scripts/migrate_images_to_oss.py --apply    # do it
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import re
import sys
from pathlib import Path

# This script prints its own report; silence the noisy SQL echo (DEBUG mode).
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import httpx  # noqa: E402
from sqlalchemy import text  # noqa: E402

from config import settings  # noqa: E402
from database import async_session  # noqa: E402
from services.image_storage import OSSImageStorage  # noqa: E402

LOCAL_PREFIX = "/static/images/"
STATIC_DIR = _BACKEND / "static" / "images"
# Match a /static/images/... path up to (and including) an image extension,
# stopping before JSON/string delimiters. Handles non-ascii (Chinese) filenames.
URL_RE = re.compile(r"/static/images/[^\s\"'\\)]+?\.(?:png|jpe?g|webp|gif|svg)", re.IGNORECASE)


async def discover_columns(session) -> list[tuple[str, str, str]]:
    """Return (table, column, data_type) for every text/json column in public schema
    that actually contains at least one '/static/images/' reference."""
    rows = await session.execute(
        text(
            """
            SELECT table_name, column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND data_type IN ('text', 'character varying', 'json', 'jsonb')
            ORDER BY table_name, column_name
            """
        )
    )
    hits: list[tuple[str, str, str]] = []
    for table, column, dtype in rows.all():
        probe = await session.execute(
            text(f'SELECT 1 FROM "{table}" WHERE "{column}"::text LIKE :m LIMIT 1'),
            {"m": "%/static/images/%"},
        )
        if probe.first() is not None:
            hits.append((table, column, dtype))
    return hits


async def collect_keys(session, columns: list[tuple[str, str, str]]) -> set[str]:
    """Extract every distinct asset key (path after /static/images/) referenced."""
    keys: set[str] = set()
    for table, column, _ in columns:
        rows = await session.execute(
            text(f'SELECT "{column}"::text FROM "{table}" WHERE "{column}"::text LIKE :m'),
            {"m": "%/static/images/%"},
        )
        for (val,) in rows.all():
            if not val:
                continue
            for match in URL_RE.findall(val):
                keys.add(match[len(LOCAL_PREFIX):])
    return keys


def oss_public_prefix(storage: OSSImageStorage) -> str:
    """Derive the public URL prefix P such that local key -> P + key."""
    probe = "__migrate_probe__"
    url = storage._public_url(probe)
    assert url.endswith(probe), f"unexpected public url shape: {url}"
    return url[: -len(probe)]


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="actually upload + rewrite (default: dry-run)")
    args = ap.parse_args()
    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"=== migrate_images_to_oss [{mode}] ===")
    print(f"backend         = {settings.image_storage_backend}")
    print(f"oss bucket      = {settings.oss_bucket_name} @ {settings.oss_endpoint}")
    print(f"static dir      = {STATIC_DIR}\n")

    async with async_session() as session:
        columns = await discover_columns(session)
        keys = await collect_keys(session, columns)

    print(f"columns containing /static/images/  : {len(columns)}")
    for t, c, d in columns:
        print(f"    - {t}.{c} ({d})")
    print(f"\ndistinct referenced assets          : {len(keys)}")

    present, missing = [], []
    for k in sorted(keys):
        (present if (STATIC_DIR / k).is_file() else missing).append(k)
    print(f"    present locally                 : {len(present)}")
    print(f"    MISSING locally                 : {len(missing)}")
    for k in missing:
        print(f"        ! missing: {k}")

    storage = OSSImageStorage()
    prefix = oss_public_prefix(storage)
    print(f"\noss public prefix                   : {prefix}")
    print(f"rewrite rule  : '{LOCAL_PREFIX}'  ->  '{prefix}'")

    if not args.apply:
        print("\n[DRY-RUN] no uploads, no DB writes. Re-run with --apply to execute.")
        return 0

    if missing:
        print(f"\nABORT: {len(missing)} referenced asset(s) missing locally — refusing to "
              "rewrite (would create dangling OSS links). Investigate first.")
        return 2

    # 1) upload referenced assets
    print(f"\nuploading {len(present)} assets to OSS ...")
    first_url = None
    for i, k in enumerate(present, 1):
        data = (STATIC_DIR / k).read_bytes()
        url = await storage.save(data, k)
        if first_url is None:
            first_url = url
        if i % 20 == 0 or i == len(present):
            print(f"    {i}/{len(present)} uploaded")

    # 2) gate: prove one object is publicly fetchable before touching the DB
    print(f"\nverifying public access: {first_url}")
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        resp = await client.get(first_url)
    ct = resp.headers.get("content-type", "")
    if resp.status_code != 200 or not ct.startswith("image/"):
        print(f"ABORT: public fetch failed (status={resp.status_code}, content-type={ct}). "
              "Bucket may not be public-read. No DB changes made.")
        return 3
    print(f"    OK  status=200  content-type={ct}  bytes={len(resp.content)}")

    # 3) rewrite every column (prefix replace), commit once
    print("\nrewriting DB references ...")
    total = 0
    async with async_session() as session:
        for table, column, dtype in columns:
            if dtype in ("json", "jsonb"):
                stmt = text(
                    f'UPDATE "{table}" SET "{column}" = '
                    f'replace("{column}"::text, :loc, :pre)::{dtype} '
                    f'WHERE "{column}"::text LIKE :m'
                )
            else:
                stmt = text(
                    f'UPDATE "{table}" SET "{column}" = replace("{column}", :loc, :pre) '
                    f'WHERE "{column}" LIKE :m'
                )
            res = await session.execute(stmt, {"loc": LOCAL_PREFIX, "pre": prefix, "m": "%/static/images/%"})
            n = res.rowcount or 0
            total += n
            print(f"    {table}.{column:<16} rows updated: {n}")
        await session.commit()
    print(f"\nDONE. uploaded={len(present)}  rows_rewritten={total}")

    # 4) post-check: any /static/images/ left?
    async with async_session() as session:
        leftover = await discover_columns(session)
    print(f"columns still containing /static/images/ : {len(leftover)}"
          + ("  (expected 0)" if not leftover else "  -- INVESTIGATE: " + str(leftover)))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
