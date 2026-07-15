"""SQLTool: Execute SQL queries against external databases.

Part 2: Stub — returns placeholder.
Part 3: Connect to MySQL, PostgreSQL, etc.
"""

from filemaker_gateway.tool.base import Tool, ToolResult


class SQLTool(Tool):
    """Execute SQL queries against external databases.

    For querying MySQL, PostgreSQL, or other databases
    that are not directly accessible from FileMaker.
    """

    @property
    def name(self) -> str:
        return "sql_query"

    @property
    def description(self) -> str:
        return (
            "Execute SQL queries against external databases (MySQL, PostgreSQL, etc.). "
            "Use for SELECT queries to read data. "
            "For INSERT, UPDATE, or DELETE, the tool will ask for confirmation. "
            "Provide the SQL query string and optionally the database name "
            "if multiple databases are configured."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The SQL query to execute.",
                },
                "database": {
                    "type": "string",
                    "description": "The database name to query (if multiple are configured).",
                },
            },
            "required": ["query"],
        }

    @property
    def read_only(self) -> bool:
        return True  # Conservative: mark as read-only, Part 3 can override

    async def execute(
        self,
        query: str,
        database: str = "default",
    ) -> ToolResult | str:
        # Part 2 stub
        # Part 3: connect to real databases
        # For safety, warn about non-SELECT queries in stub
        query_upper = query.strip().upper()
        if query_upper.startswith(("INSERT", "UPDATE", "DELETE", "DROP", "ALTER")):
            return ToolResult.error(
                f"Write operations are not available in Part 2 stub. Query: {query[:80]}..."
            )

        return str(
            ToolResult(
                f"[SQLTool - STUB] database={database}, query={query[:100]}... "
                f"Part 3 will execute against real database."
            )
        )
