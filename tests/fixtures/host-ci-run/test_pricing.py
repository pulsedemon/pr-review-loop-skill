from pricing import bulk_discount


def test_small_order_pays_full_price():
    assert bulk_discount(5, 100) == 500


def test_large_order_gets_discount():
    assert bulk_discount(11, 100) == 990


def test_threshold_order_gets_discount():
    assert bulk_discount(10, 100) == 900
