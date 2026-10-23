"""Compatibility entry point and opt-in six-hour scheduler."""

import argparse
import json
import logging
import sys
import time

import schedule

from cli import add_collection_arguments, configure_logging, run_safely, settings_for
from config import COLLECTION_INTERVAL_HOURS
from pipeline import run_pipeline


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run Metis once or every six hours")
    parser.add_argument("--watch", action="store_true")
    add_collection_arguments(parser)
    args = parser.parse_args(argv)
    configure_logging()

    def run():
        result = run_safely(
            lambda: run_pipeline(
                settings_for(
                    args.sources,
                    args.comment_threads,
                    args.comments_per_thread,
                    args.audiences,
                ),
                limit=args.limit,
                days=args.days,
            )
        )
        print(json.dumps(result), flush=True)
        return {"success": 0, "partial": 2, "error": 1}[result["status"]]

    status = run()
    if args.watch:
        scheduler = schedule.Scheduler()
        scheduler.every(COLLECTION_INTERVAL_HOURS).hours.do(run)
        logging.info(
            "Scheduled every %s hours while this process remains running",
            COLLECTION_INTERVAL_HOURS,
        )
        try:
            while True:
                scheduler.run_pending()
                time.sleep(1)
        except KeyboardInterrupt:
            return 0
    return status


if __name__ == "__main__":
    sys.exit(main())
