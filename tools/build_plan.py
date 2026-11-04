"""Build code/plan.json from the version evidence and the computed applied spacing.

    python tools/build_plan.py <registration_template_versions.csv> <spacing_plan.json> <record cache dir>

The cache holds the published records as <dataset>/<file>, read anonymously from S3.
"""

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from correction import OLD_LABEL, processes

FILES = ("ccf_alignment/processing.json", "processing.json")


def main(evidence: str, spacing_file: str, cache: str) -> None:
    spacing = json.loads(Path(spacing_file).read_text())
    plan = []
    with open(evidence, newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        subject, dataset = row["subject"], row["registered_dataset"]
        steps = spacing.get(subject, {}).get("steps", {})
        for name in FILES:
            path = Path(cache) / dataset / name
            if not path.is_file():
                continue
            doc = json.loads(path.read_text())
            relabel = row["template_to_ccf_used"] == "v1.5" and OLD_LABEL in json.dumps(doc)
            names = {p.get("name") for p in processes(doc)}
            file_spacing = {k: v for k, v in steps.items() if k in names}
            if relabel or file_spacing:
                plan.append(
                    {
                        "subject": subject,
                        "dataset": dataset,
                        "file": name,
                        "relabel": relabel,
                        "spacing": file_spacing,
                        "evidence": row["evidence"],
                    }
                )
    out = Path(__file__).resolve().parents[1] / "code" / "plan.json"
    out.write_text(json.dumps(plan, indent=2) + "\n")
    print(f"{len(plan)} files planned -> {out}")


if __name__ == "__main__":
    main(*sys.argv[1:4])
