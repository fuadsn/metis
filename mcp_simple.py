#!/usr/bin/env python3
"""
Metis MCP Server - Alternative for Python 3.9
Uses stdio-based tool calls instead of MCP SDK
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from mcp_server import collect_posts, run_analysis, get_ideas, get_clusters


def main():
    if len(sys.argv) < 2:
        print(
            json.dumps(
                {
                    "error": "Usage: python mcp.py <command> [args]",
                    "commands": ["collect", "analyze", "ideas", "clusters"],
                }
            )
        )
        sys.exit(1)

    command = sys.argv[1]

    if command == "collect":
        result = collect_posts()
    elif command == "analyze":
        result = run_analysis()
    elif command == "ideas":
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        result = get_ideas(limit)
    elif command == "clusters":
        result = get_clusters()
    else:
        result = {"error": f"Unknown command: {command}"}

    print(json.dumps(result))


if __name__ == "__main__":
    main()
