"""Write the API's OpenAPI schema to a JSON file (PlaceChat Technical Design §7.1).

The frontend turns the schema into TypeScript types with `npm run api-types`, and CI fails if the
committed types are out of date. Run from backend/ after changing any route or Pydantic model:

    python scripts/export_openapi.py ../frontend/openapi.json

Building the schema does not connect to the database, so no .env values are needed.
"""

import json
import sys
from pathlib import Path

from app.main import create_app


def main() -> None:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("openapi.json")
    schema = create_app().openapi()
    target.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {target}")


if __name__ == "__main__":
    main()
