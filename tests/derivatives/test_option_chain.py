from quantmind.derivatives import OptionContract, OptionType, option_chain_from_upstox


def test_option_chain_parser():
    raw = {
        "data": {
            "expiry_dates": ["2024-08-29", "2024-09-26"],
            "strike_prices": ["2500", "2600"],
        }
    }
    chain = option_chain_from_upstox(raw, "RELIANCE")
    assert len(chain) == 8  # 2 expiry * 2 strike * 2 option types
    assert all(isinstance(c, OptionContract) for c in chain)
    assert any(c.option_type == OptionType.CALL for c in chain)
    assert any(c.option_type == OptionType.PUT for c in chain)
