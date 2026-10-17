# retrieval/falkordb_client.py
"""Client for querying FalkorDB graph."""

import os
from typing import Any

from dotenv import load_dotenv

import config

def _plain(
    value: Any
) -> Any:
    # nodes and edges become their properties (plus labels / type), so every row is plain data
    if hasattr(value, "properties") and hasattr(value, "labels"):
        return {**value.properties, "_labels": list(value.labels or [])}
    if hasattr(value, "properties") and hasattr(value, "relation"):
        return {**value.properties, "_type": value.relation}
    if isinstance(value, list):
        return [_plain(item) for item in value]
    return value

def rows_as_dicts(
    result: Any
) -> list[dict]:
    # result.header is [[column type, column name], ...]; result_set is one list of values per row
    columns = [column[1] if isinstance(column, (list, tuple)) else column for column in result.header or []]
    return [dict(zip(columns, (_plain(value) for value in row))) for row in result.result_set or []]

class FalkorDBClient:
    """Parameterised queries against one graph; rows come back as dicts keyed by column name."""

    def __init__(
        self,
        url: str | None = None,
        graph_name: str | None = None,
        graph: Any = None
    ):
        self.url = url or os.getenv("FALKORDB_URL") or config.FALKORDB_URL
        self.graph_name = graph_name or os.getenv("FALKORDB_GRAPH_NAME") or config.FALKORDB_GRAPH_NAME
        self.graph = graph
        if self.graph is not None:
            return

        try:
            from falkordb import FalkorDB
            # redis://[:password@]host:port/db
            db = FalkorDB.from_url(self.url, socket_connect_timeout=3)
            db.connection.ping()
            self.graph = db.select_graph(self.graph_name)
        except Exception as e:
            print(f"Warning: FalkorDB not available at {self.url}: {e}")

    @property
    def available(self) -> bool:
        return self.graph is not None

    def query(
        self,
        cypher: str,
        params: dict | None = None
    ) -> list[dict]:
        """Run a READ-ONLY query with $parameters. No database: [] (with the warning above). Bad query: raises."""
        if not self.available:
            return []
        return rows_as_dicts(self.graph.ro_query(cypher, params or {}))

_client = None


def get_client():
    """Lazy load FalkorDB client."""
    global _client
    if _client is None or not _client.available:
        # an unavailable client is not kept: the database may come up later in a long-running process
        load_dotenv()
        _client = FalkorDBClient()
    return _client
