#!/usr/bin/env python3
"""Compatibility wrapper for the original JSON command adapter."""

import sys

from cli import main

if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) == 2 and args[0] == "ideas" and args[1].isdigit():
        args = ["ideas", "--limit", args[1]]
    raise SystemExit(main(args))
