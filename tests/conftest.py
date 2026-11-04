"""Fixtures: real published records, and an in-memory stand-in for S3."""

import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

RESOURCES = Path(__file__).parent / "resources"
PLAN = json.loads((Path(__file__).resolve().parents[1] / "code" / "plan.json").read_text())


def record(subject: str, file: str = "ccf_alignment/processing.json") -> bytes:
    """A published record for a subject, as read from S3."""
    (path,) = [p for p in RESOURCES.glob(f"*_{subject}_*/{file}")]
    return path.read_bytes()


def planned(subject: str, file: str = "ccf_alignment/processing.json") -> dict:
    """The plan entry for one record."""
    return next(p for p in PLAN if p["subject"] == subject and p["file"] == file)


class FakeS3:
    """Enough of a boto3 S3 client for the capsule: objects, ETags, NoSuchKey."""

    class exceptions:
        class NoSuchKey(Exception):
            pass

    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self.puts: list[str] = []

    def get_object(self, Bucket, Key):
        if Key not in self.objects:
            raise self.exceptions.NoSuchKey(Key)
        body = self.objects[Key]
        return {"Body": _Body(body), "ETag": f'"{hashlib.md5(body).hexdigest()}"'}

    def put_object(self, Bucket, Key, Body, ContentType):
        self.objects[Key] = Body
        self.puts.append(Key)


class _Body:
    def __init__(self, data: bytes):
        self.data = data

    def read(self) -> bytes:
        return self.data


@pytest.fixture
def s3():
    """S3 holding the fixture records under their published keys."""
    client = FakeS3()
    for path in RESOURCES.rglob("*.json"):
        client.objects[path.relative_to(RESOURCES).as_posix()] = path.read_bytes()
    return client
