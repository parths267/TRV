"""Yahoo chart URLs must survive symbols that contain reserved characters."""
from tradingview_mcp.core.utils.yahoo_symbols import encode_yahoo_symbol


def test_ampersand_is_encoded_and_dot_and_caret_are_kept():
    assert encode_yahoo_symbol("M&M.NS") == "M%26M.NS"
    assert encode_yahoo_symbol("^NSEI") == "^NSEI"
    assert encode_yahoo_symbol("RELIANCE.NS") == "RELIANCE.NS"
    assert encode_yahoo_symbol(" BAJAJ-AUTO.NS ") == "BAJAJ-AUTO.NS"
