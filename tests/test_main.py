"""Dry run, write and restore against a stand-in for S3."""

import csv

import main
import pytest

SUBJECT = "841260"


def args(tmp_path, *extra):
    return main.parse_args(["--results-dir", str(tmp_path / "dry"), *extra])


def dry(s3, tmp_path):
    before = dict(s3.objects)
    assert main.run(args(tmp_path, "--subjects", SUBJECT), s3) == 0
    assert s3.objects == before and not s3.puts
    return list(csv.DictReader(open(tmp_path / "dry" / "manifest.csv")))


def test_a_dry_run_writes_nothing_to_s3_and_records_both_files(s3, tmp_path):
    rows = dry(s3, tmp_path)
    assert sorted(r["file"] for r in rows) == ["ccf_alignment/processing.json", "processing.json"]
    assert all(r["status"] == "change" for r in rows)
    for name in ("original.json", "corrected.json", "diff.txt"):
        assert len(list((tmp_path / "dry").rglob(f"*.{name}"))) == 2


def test_write_applies_exactly_the_reviewed_files(s3, tmp_path):
    rows = dry(s3, tmp_path)
    write = args(
        tmp_path, "--mode", "write", "--subjects", SUBJECT, "--dry-run-dir", str(tmp_path / "dry")
    )
    assert main.run(write, s3) == 0
    assert sorted(s3.puts) == sorted(f"{r['dataset']}/{r['file']}" for r in rows)
    for r in rows:
        assert main.sha(s3.objects[f"{r['dataset']}/{r['file']}"]) == r["corrected_sha256"]


def test_a_record_changed_since_the_dry_run_is_skipped(s3, tmp_path):
    rows = dry(s3, tmp_path)
    key = f"{rows[0]['dataset']}/{rows[0]['file']}"
    s3.objects[key] = s3.objects[key] + b" "
    write = args(
        tmp_path, "--mode", "write", "--subjects", SUBJECT, "--dry-run-dir", str(tmp_path / "dry")
    )
    assert main.run(write, s3) == 1
    assert key not in s3.puts and len(s3.puts) == 1


def test_restore_puts_back_the_exact_originals(s3, tmp_path):
    originals = dict(s3.objects)
    dry(s3, tmp_path)
    common = ["--subjects", SUBJECT, "--dry-run-dir", str(tmp_path / "dry")]
    assert main.run(args(tmp_path, "--mode", "write", *common), s3) == 0
    assert main.run(args(tmp_path, "--mode", "restore", *common), s3) == 0
    assert s3.objects == originals


def test_writing_without_a_dry_run_is_refused(s3, tmp_path):
    with pytest.raises(SystemExit, match="dry-run-dir"):
        main.run(args(tmp_path, "--mode", "write"), s3)
    (tmp_path / "empty").mkdir()
    with pytest.raises(SystemExit, match="run a dry run first"):
        main.run(args(tmp_path, "--mode", "write", "--dry-run-dir", str(tmp_path / "empty")), s3)


def test_an_unplanned_subject_is_refused(s3, tmp_path):
    with pytest.raises(SystemExit, match="Not in the plan"):
        main.run(args(tmp_path, "--subjects", "754611"), s3)
