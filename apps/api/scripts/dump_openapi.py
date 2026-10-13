"""Write the FastAPI OpenAPI schema to a file (used by `make types`; no running server needed)."""

import json
import sys
from pathlib import Path

from app.main import app

out = Path(sys.argv[1])
out.write_text(json.dumps(app.openapi(), indent=2) + "\n", encoding="utf-8")
print(f"wrote {out}")
