"""Corrections to published registration records, and the checks that they change nothing else."""

from __future__ import annotations

import json

OLD_LABEL = "reg_exaspim_template_to_ccf_25um_v1.4"
NEW_LABEL = "reg_exaspim_template_to_ccf_25um_v1.5"
LABEL_FIELDS = ("template_to_ccf_transforms", "ccf_to_template_fwd", "ccf_to_template_transforms")
SPACING_FIELD = "applied_spacing_mm"


class CorrectionError(ValueError):
    """Raised when a correction would change more than intended."""


def load(raw: bytes) -> tuple[dict, bool]:
    """Parse a record, and note whether it ends in a newline."""
    return json.loads(raw), raw.endswith(b"\n")


def dump(doc: dict, trailing_newline: bool) -> bytes:
    """Serialise in the published records' format: indent 3, ASCII."""
    return json.dumps(doc, indent=3, ensure_ascii=True).encode() + (
        b"\n" if trailing_newline else b""
    )


def processes(doc: dict) -> list[dict]:
    """The record's processes, in either schema."""
    return (
        doc.get("data_processes")
        or (doc.get("processing_pipeline") or {}).get("data_processes")
        or []
    )


def parameters(process: dict) -> dict:
    """A process's parameters, in either schema."""
    return (process.get("code") or {}).get("parameters") or process.get("parameters") or {}


def relabel(doc: dict) -> int:
    """Replace the v1.4 label with v1.5 in the template-transform fields and notes."""
    count = 0
    for process in processes(doc):
        params = parameters(process)
        for field in LABEL_FIELDS:
            paths = params.get(field)
            if isinstance(paths, list):
                count += sum(p.count(OLD_LABEL) for p in paths if isinstance(p, str))
                params[field] = [
                    p.replace(OLD_LABEL, NEW_LABEL) if isinstance(p, str) else p for p in paths
                ]
        notes = process.get("notes")
        if isinstance(notes, str) and OLD_LABEL in notes:
            count += notes.count(OLD_LABEL)
            process["notes"] = notes.replace(OLD_LABEL, NEW_LABEL)
    return count


def add_spacing(doc: dict, spacing: dict[str, list[float]]) -> int:
    """Add the applied spacing to the named atlas-alignment steps."""
    added = 0
    for process in processes(doc):
        values = spacing.get(process.get("name"))
        if values is None:
            continue
        registration = parameters(process).get("sample_to_template_registration")
        if not isinstance(registration, dict):
            raise CorrectionError(f"{process['name']} has no sample_to_template_registration")
        if registration.get(SPACING_FIELD) == values:
            continue
        if SPACING_FIELD in registration:
            raise CorrectionError(f"{process['name']} already has a different {SPACING_FIELD}")
        if sorted(values) != sorted(registration["sample_scale"]):
            raise CorrectionError(
                f"{process['name']}: {values} is not a reordering of sample_scale"
            )
        registration[SPACING_FIELD] = values
        added += 1
    return added


def diff(old: object, new: object, path: str = "") -> list[tuple[str, object, object]]:
    """Every difference between two documents, as (path, old, new)."""
    if isinstance(old, dict) and isinstance(new, dict):
        out = []
        for key in dict.fromkeys([*old, *new]):
            out += diff(old.get(key, "<absent>"), new.get(key, "<absent>"), f"{path}.{key}")
        return out
    if isinstance(old, list) and isinstance(new, list) and len(old) == len(new):
        return [d for i, (a, b) in enumerate(zip(old, new)) for d in diff(a, b, f"{path}[{i}]")]
    return [] if old == new else [(path, old, new)]


def check(original: dict, corrected: dict) -> list[str]:
    """Reasons the correction is unsafe; empty when only the intended fields changed."""
    problems = []
    for path, old, new in diff(original, corrected):
        leaf = path.rsplit(".", 1)[-1].split("[")[0]
        if leaf == SPACING_FIELD and old == "<absent>":
            continue
        if (
            isinstance(old, str)
            and isinstance(new, str)
            and (leaf in LABEL_FIELDS or leaf == "notes")
            and old.replace(OLD_LABEL, NEW_LABEL) == new
        ):
            continue
        problems.append(f"unexpected change at {path}")
    text = json.dumps(corrected)
    if OLD_LABEL in text and NEW_LABEL in text:
        problems.append("both labels remain after relabelling")
    return problems


def correct(
    raw: bytes, relabel_record: bool, spacing: dict[str, list[float]]
) -> tuple[bytes, dict]:
    """Apply the planned corrections to one record.

    Returns the corrected bytes and a summary; raises if the result would change anything
    beyond the planned fields.
    """
    original, newline = load(raw)
    if dump(original, newline) != raw:
        raise CorrectionError("the record does not re-serialise byte for byte")
    corrected = json.loads(raw)
    relabels = relabel(corrected) if relabel_record else 0
    if relabel_record and OLD_LABEL in json.dumps(corrected):
        raise CorrectionError("the v1.4 label remains outside the expected fields")
    added = add_spacing(corrected, spacing) if spacing else 0
    problems = check(original, corrected)
    if problems:
        raise CorrectionError("; ".join(problems))
    return dump(corrected, newline), {"relabels": relabels, "spacing_added": added}
