# exaspim-registration-metadata-correction

Corrects published registration records on `aind-open-data`, exactly as listed in
`code/plan.json` (65 files):

- `reg_exaspim_template_to_ccf_25um_v1.4` → `…_v1.5` in `template_to_ccf_transforms`,
  `ccf_to_template_fwd`, `ccf_to_template_transforms` and `notes`, for the 56 registrations
  whose run mounted v1.5 at the v1.4 path (evidence: `tools/registration_template_versions.csv`).
- `applied_spacing_mm` added to `sample_to_template_registration` on both atlas-alignment
  steps, for 9 registrations (`tools/spacing_plan.json`).

## App Panel

| # | Parameter | Values |
|---|---|---|
| 1 | `mode` | `dry_run` (default), `write`, `restore` |
| 2 | `subjects` | comma-separated, e.g. `841260`; blank for all planned |
| 3 | `dry_run_dir` | for `write`/`restore`: the dry run's results, e.g. `/data/<dry run asset>` |

- **dry_run** writes each record's original, corrected and diff, and `manifest.csv`, to
  `/results`. Nothing is written to S3.
- **write** uploads the reviewed corrections. A record whose content or ETag changed since
  the dry run is skipped. Each upload is read back and compared.
- **restore** puts the dry run's originals back, only where the record is still the corrected one.

A correction is refused if the record does not re-serialise byte for byte, if any field
other than those above would change, or if a spacing is not a reordering of `sample_scale`.

## Tests

```bash
python -m pytest
python tools/verify_all.py <cache of the published records> --schema --reader
```
