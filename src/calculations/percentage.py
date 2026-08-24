def pct_change(current: float, previous_close: float) -> float:
    """Percentage change from the previous close.

    Used for both sector indices and individual stocks:
    ((current - previous_close) / previous_close) * 100
    """
    return ((current - previous_close) / previous_close) * 100
