from datetime import UTC, datetime, timedelta

_ONE_MILLISECOND = timedelta(milliseconds=1)


def utc_now() -> datetime:
    """Return timezone-aware UTC now."""
    return datetime.now(UTC)


def elapsed_ms(started_at: datetime, finished_at: datetime) -> int:
    """How long between two instants, in whole milliseconds, never negative.

    The one owner of that meaning. It lived twice before -- once in the
    chat-progress rebuild and once in the job registry -- and both copies
    scaled ``total_seconds()`` by a thousand and truncated. Seconds as a
    ``float`` cannot represent every millisecond, so that product lands just
    below a whole number and the truncation loses one: 1482 of the first
    200 001 whole-millisecond spans came out low, the first at 1001 ms. Floor
    division on the ``timedelta`` itself puts no float in the path at all.

    A span finer than a millisecond truncates down rather than rounding up, so
    a reading here never exceeds what the browser -- which cannot see below a
    millisecond -- would report for the same pair.
    """
    return max(0, (finished_at - started_at) // _ONE_MILLISECOND)
