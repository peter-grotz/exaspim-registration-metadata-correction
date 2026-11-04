"""Correct published registration records on aind-open-data, as planned in plan.json.

Modes:
  dry_run  read each planned record, write original, corrected and diff to /results, plus
           manifest.csv. Writes nothing to S3.
  write    apply a reviewed dry run: for each manifest row, re-read the record, require its
           ETag and content to match the manifest, upload the corrected record, verify it.
  restore  put a dry run's originals back, only where the record is still the corrected one.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import sys
from pathlib import Path

from correction import CorrectionError, correct, diff, load

BUCKET = "aind-open-data"
PLAN = Path(__file__).with_name("plan.json")
FIELDS = [
    "subject",
    "dataset",
    "file",
    "etag",
    "original_sha256",
    "corrected_sha256",
    "relabels",
    "spacing_added",
    "status",
]

logger = logging.getLogger("correction")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mode", choices=("dry_run", "write", "restore"), default="dry_run")
    parser.add_argument(
        "--subjects", default="", help="Comma-separated subjects; blank for all planned."
    )
    parser.add_argument(
        "--dry-run-dir", type=Path, help="Results of the dry run to write or restore."
    )
    parser.add_argument("--results-dir", type=Path, default=Path("../results"))
    return parser.parse_args(argv)


def read(client, key: str) -> tuple[bytes, str]:
    obj = client.get_object(Bucket=BUCKET, Key=key)
    return obj["Body"].read(), obj["ETag"]


def dry_run(client, plan: list[dict], results: Path) -> int:
    rows, failed = [], 0
    for entry in plan:
        key = f"{entry['dataset']}/{entry['file']}"
        out = results / entry["dataset"] / entry["file"]
        out.parent.mkdir(parents=True, exist_ok=True)
        row = {"subject": entry["subject"], "dataset": entry["dataset"], "file": entry["file"]}
        try:
            raw, etag = read(client, key)
            fixed, summary = correct(raw, entry["relabel"], entry["spacing"])
        except (CorrectionError, client.exceptions.NoSuchKey) as error:
            rows.append({**row, "status": f"failed: {error}"})
            failed += 1
            logger.error("%s: %s", key, error)
            continue
        out.with_suffix(".original.json").write_bytes(raw)
        out.with_suffix(".corrected.json").write_bytes(fixed)
        changes = diff(load(raw)[0], load(fixed)[0])
        out.with_suffix(".diff.txt").write_text(
            "".join(f"{path}\n  - {old}\n  + {new}\n" for path, old, new in changes)
        )
        status = "change" if changes else "unchanged"
        rows.append(
            {
                **row,
                "etag": etag,
                "original_sha256": sha(raw),
                "corrected_sha256": sha(fixed),
                **summary,
                "status": status,
            }
        )
        logger.info("%s: %s, %s", key, status, summary)
    with open(results / "manifest.csv", "w", newline="") as handle:
        writer = csv.DictWriter(handle, FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    logger.info(
        "%d records: %d to change, %d failed",
        len(rows),
        sum(r["status"] == "change" for r in rows),
        failed,
    )
    return 1 if failed else 0


def manifest(dry_run_dir: Path) -> list[dict]:
    path = dry_run_dir / "manifest.csv"
    if not path.is_file():
        raise SystemExit(f"No manifest.csv in {dry_run_dir}; run a dry run first")
    return [r for r in csv.DictReader(open(path)) if r["status"] == "change"]


def write(client, rows: list[dict], dry_run_dir: Path, restore: bool) -> int:
    skipped = 0
    for row in rows:
        key = f"{row['dataset']}/{row['file']}"
        local = dry_run_dir / row["dataset"] / row["file"]
        expected_now = row["corrected_sha256"] if restore else row["original_sha256"]
        body = local.with_suffix(".original.json" if restore else ".corrected.json").read_bytes()
        target = row["original_sha256"] if restore else row["corrected_sha256"]
        raw, etag = read(client, key)
        if sha(raw) != expected_now or (not restore and etag != row["etag"]):
            logger.warning("%s changed since the dry run; skipped", key)
            skipped += 1
            continue
        if sha(body) != target:
            raise SystemExit(f"{local}: file does not match the manifest")
        client.put_object(Bucket=BUCKET, Key=key, Body=body, ContentType="application/json")
        if sha(read(client, key)[0]) != target:
            raise SystemExit(f"{key}: read-back does not match what was written")
        logger.info("%s: %s", key, "restored" if restore else "corrected")
    logger.info("%d written, %d skipped", len(rows) - skipped, skipped)
    return 1 if skipped else 0


def run(args: argparse.Namespace, client) -> int:
    plan = json.loads(PLAN.read_text())
    wanted = {s.strip() for s in args.subjects.split(",") if s.strip()}
    plan = [p for p in plan if not wanted or p["subject"] in wanted]
    if wanted - {p["subject"] for p in plan}:
        raise SystemExit(f"Not in the plan: {sorted(wanted - {p['subject'] for p in plan})}")
    if args.mode == "dry_run":
        args.results_dir.mkdir(parents=True, exist_ok=True)
        return dry_run(client, plan, args.results_dir)
    if not args.dry_run_dir:
        raise SystemExit("--dry-run-dir is required to write or restore")
    keys = {(p["dataset"], p["file"]) for p in plan}
    rows = [r for r in manifest(args.dry_run_dir) if (r["dataset"], r["file"]) in keys]
    return write(client, rows, args.dry_run_dir, restore=args.mode == "restore")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    import boto3

    return run(parse_args(), boto3.client("s3"))


if __name__ == "__main__":
    sys.exit(main())
