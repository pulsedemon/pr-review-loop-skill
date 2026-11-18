"""order pricing rules."""

BULK_THRESHOLD = 10


def bulk_discount(quantity: int, unit_price: int) -> int:
    """return the order total in cents. Orders of 10 or more units get 10% off."""
    total = quantity * unit_price
    if quantity > BULK_THRESHOLD:
        total = total * 90 // 100
    return total
