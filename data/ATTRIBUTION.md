# Data attribution

* `mache_signals.csv` is a flattened export of `signalsets/v3/default.json` from the
  [OBDb/Ford-Mustang-Mach-E](https://github.com/OBDb/Ford-Mustang-Mach-E) repository
  (commit 38e4bed, 2026-11-10), licensed **CC BY-SA 4.0**. This file is therefore also
  CC BY-SA 4.0. Columns: request header (`hdr`), response header (`rax`), UDS DID (`did`),
  signal id/name, bit index and length inside the DID payload (`bix`, `len`), scaling
  (`value = raw * mul / div + add`), signedness, unit, range, enum map, and OBDb's debug /
  model-year filter flags (`dbg`, `filter`). A `filter` of `{"from": 2027}` means OBDb has
  *not yet verified* the signal for any current model year; `{"years":[2025], "from":2027}`
  means a 2025 car was probed and did **not** answer that DID (see docs).
* `modules.json` module addresses come from
  [sillygoose/mme-record](https://github.com/sillygoose/mme-record) (`source/json/module/modules.json`, MIT).
* `tests/fixtures_obdb.json` is converted from the OBDb repository's `tests/test_cases/*/commands/*.yaml`
  (real responses captured from owners' cars; CC BY-SA 4.0).
