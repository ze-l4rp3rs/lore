import json
import os
import time
from dataclasses import asdict, is_dataclass
from typing import Any

import config

def _slug(
    text: str
) -> str:
    name = ""
    for letter in text.lower():
        if letter.isalnum():
            name += letter
        elif not name.endswith("_"):
            name += "_"
    return name.strip("_")[:40] or "question"

def _plain(
    value: Any
) -> Any:
    # dataclasses (traces, sources, tool calls) become dicts so the whole run serialises as JSON
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    return str(value)

class RunLogger:
    """One run = one <timestamp>_<question>.json (every step, in order) plus the .md answer."""

    def __init__(
        self,
        question: str
    ):
        os.makedirs(config.RUNS_FOLDER, exist_ok=True)
        self.path = os.path.join(config.RUNS_FOLDER, time.strftime("%Y%m%d_%H%M%S") + "_" + _slug(question))
        self.record: dict[str, Any] = {"question": question, "steps": []}

    def step(
        self,
        name: str,
        **data: Any
    ):
        self.record["steps"].append({"step": name, **data})

    def save(
        self,
        result: dict[str, Any] | None = None,
        markdown: str = ""
    ):
        self.record["result"] = result
        with open(self.path + ".json", "w", encoding="utf-8") as file:
            json.dump(self.record, file, indent=2, ensure_ascii=False, default=_plain)
            file.write("\n")
        if markdown:
            with open(self.path + ".md", "w", encoding="utf-8") as file:
                file.write(markdown + "\n")
