from __future__ import annotations
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];TASK=ROOT/'task';EXPECTED=json.loads((ROOT/'qa/expected_hashes.json').read_text(encoding='utf-8'))
actual={name:hashlib.sha256((TASK/name).read_bytes()).hexdigest() for name in EXPECTED}
if actual!=EXPECTED:raise SystemExit(f'attachment hash mismatch: {actual}')
(ROOT/'evidence/attachment-hashes.json').write_text(json.dumps(actual,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
