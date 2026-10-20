"""Export widget and event contracts as JSON Schema for the web app (`make contracts`)."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, TypeAdapter

from agent.widgets import Widget, WidgetEvent

OUT = Path(__file__).resolve().parents[1] / "web" / "src" / "contracts"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    models: dict[str, type[BaseModel]] = {"widget": Widget, "widget_event": WidgetEvent}
    for name, model in models.items():
        schema = TypeAdapter(model).json_schema(mode="serialization")
        (OUT / f"{name}.schema.json").write_text(json.dumps(schema, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
