"""Read a local sample directory; save OCR evidence without copying photographs."""
import argparse
import json
import time
from pathlib import Path

from app.recognition import LocalScanner, combine_fields

parser = argparse.ArgumentParser()
parser.add_argument('directory', type=Path)
parser.add_argument('output', type=Path)
args = parser.parse_args()
scanner = LocalScanner()
results = []
for path in sorted(args.directory.iterdir()):
    if path.suffix.lower() not in {'.jpg', '.jpeg', '.png', '.webp'}:
        continue
    started = time.perf_counter()
    evidence = scanner(path)
    fields, conflicts = combine_fields([evidence])
    result = {'file': path.name, 'seconds': round(time.perf_counter() - started, 2),
              'fields': fields, 'conflicts': conflicts, 'evidence': evidence}
    results.append(result)
    args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'evidence'}, ensure_ascii=False), flush=True)
