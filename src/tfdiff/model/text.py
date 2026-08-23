def shortlist(items: list[str] | tuple[str, ...], shown: int) -> str:
    """Join the first `shown` items and say how many are left: `a, b, c and 4 more`."""
    listed = ", ".join(items[:shown])
    if len(items) > shown:
        listed += f" and {len(items) - shown} more"
    return listed
