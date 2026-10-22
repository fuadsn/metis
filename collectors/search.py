"""Bounded, separate recent and historical samples; never imply full coverage."""

from datetime import datetime, timezone


def age_windows(days, now=None):
    now = int(now if now is not None else datetime.now(timezone.utc).timestamp())
    cutoff = now - days * 86400
    boundary = now - min(days, 30) * 86400
    windows = [("recent", boundary, now)]
    if days > 30:
        windows.append(("historical", cutoff, boundary - 1))
    return windows


def interleave(batches):
    for index in range(max((len(batch) for batch in batches), default=0)):
        for batch in batches:
            if index < len(batch):
                yield batch[index]
