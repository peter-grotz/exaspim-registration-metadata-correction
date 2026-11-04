"""Correct every planned record from a local cache and check each result.

    python tools/verify_all.py <record cache dir> [--schema] [--reader]

--schema validates each corrected v2 record with the installed aind-data-schema;
--reader checks exaspim_swc_processing reads v1.5 and the same geometry from it.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from correction import NEW_LABEL, OLD_LABEL, correct, diff, load

PLAN = json.loads((Path(__file__).resolve().parents[1] / "code" / "plan.json").read_text())


def main(cache: str, schema: bool, reader: bool) -> int:
    failures = 0
    for entry in PLAN:
        raw = (Path(cache) / entry["dataset"] / entry["file"]).read_bytes()
        label = f"{entry['subject']} {entry['file']}"
        try:
            fixed, summary = correct(raw, entry["relabel"], entry["spacing"])
            assert summary["relabels"] == raw.decode().count(OLD_LABEL), "relabel count"
            assert (
                fixed.decode().count(NEW_LABEL)
                == raw.decode().count(NEW_LABEL) + summary["relabels"]
            )
            assert summary["spacing_added"] == len(entry["spacing"]), "spacing count"
            assert correct(fixed, entry["relabel"], entry["spacing"])[0] == fixed, "not idempotent"
            assert diff(load(raw)[0], load(fixed)[0]), "no change"
            doc = load(fixed)[0]
            if schema and str(doc.get("schema_version", "")).startswith("2"):
                from aind_data_schema.core.processing import Processing

                Processing.model_validate(doc)
            if reader and entry["file"] == "ccf_alignment/processing.json":
                from exaspim_swc_processing import registration as R

                if entry["relabel"]:
                    assert R.recorded_template_to_ccf(doc) == NEW_LABEL, "reader version"
                try:
                    before = R.parse_registration_record(load(raw)[0])
                except R.RegistrationRecordError:
                    before = None
                if before is not None:
                    assert R.parse_registration_record(doc) == before, "geometry changed"
        except Exception as error:  # noqa: BLE001 - report every record
            failures += 1
            print(f"FAIL {label}: {type(error).__name__}: {error}")
    print(f"{len(PLAN) - failures}/{len(PLAN)} planned records pass")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], "--schema" in sys.argv, "--reader" in sys.argv))
