import inspect
import json
import os
from datetime import datetime
from typing import Any, Callable

_HERE = os.path.dirname(__file__)

# A tool is a plain function plus a <name>.json schema next to it. Graph tools return Evidence (one per
# graph row or node) so each becomes its own citable source, and raise on failure (an error is never a
# source). A tool that declares a `user` parameter receives the asking user's identity and must only
# return what that user may see.


def get_time() -> str:
    now = datetime.now()
    return now.strftime("%Y-%m-%d:%H-%M")


def falkordb_query(query: str):
    # imported on first use, so the database driver is only needed when the tool is called
    from src.tools.falkordb_query import falkordb_query as _query
    return _query(query)


AVAILABLE_FUNCTIONS: dict[str, Callable[..., Any]] = {
    "get_time": get_time,
    "falkordb_query": falkordb_query,
}


def call_tool(
    name: str,
    arguments: dict,
    user: Any = None
) -> Any:
    function = AVAILABLE_FUNCTIONS[name]
    if "user" in arguments:
        raise ValueError("'user' is set by the system, not by the model")
    if "user" in inspect.signature(function).parameters:
        return function(**arguments, user=user)
    return function(**arguments)


def _load_schemas() -> list[dict]:
    schemas = []
    for filename in sorted(os.listdir(_HERE)):
        if filename.endswith(".json"):
            with open(os.path.join(_HERE, filename), encoding="utf-8") as file:
                schemas.append(json.load(file))
    return schemas


TOOL_SCHEMAS: list[dict] = _load_schemas()
