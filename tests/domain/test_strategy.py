import pytest

from quantmind.domain import DataSource, PositionSize, TradingStrategy
from quantmind.domain.exceptions import ConfigurationError, StrategyError
from quantmind.domain.models import Interval, TimeUnit


def test_strategy_uses_defaults():
    s = TradingStrategy(symbols=["RELIANCE"])
    assert s.time_unit == TimeUnit.DAY
    assert s.interval == 1


def test_strategy_basic_construction():
    s = TradingStrategy(
        time_unit=TimeUnit.DAY,
        interval=1,
        symbols=["RELIANCE"],
        position_sizes=[PositionSize(symbol="RELIANCE", percentage_of_portfolio=100)],
    )
    assert s.strategy_id == "TradingStrategy"
    assert s.market == "NSE"
    assert s.long_only is True


def test_strategy_time_unit_from_string():
    s = TradingStrategy(
        time_unit="day",
        interval=1,
        symbols=["RELIANCE"],
    )
    assert s.time_unit == TimeUnit.DAY


def test_strategy_scheduling_interval_validation():
    ds = DataSource(symbol="RELIANCE", interval=Interval.DAY)
    with pytest.raises(StrategyError):
        TradingStrategy(
            time_unit=TimeUnit.HOUR,
            interval=1,
            symbols=["RELIANCE"],
            data_sources=[ds],
        )


def test_strategy_parameters_roundtrip():
    s = TradingStrategy(time_unit="day", interval=1, symbols=["RELIANCE"])
    s.set_parameters({"fast": 10, "slow": 20, "nested": {"a": 1}})
    assert s.get_parameters() == {"fast": 10, "slow": 20, "nested": {"a": 1}}


def test_strategy_parameters_drop_non_serializable():
    s = TradingStrategy(time_unit="day", interval=1, symbols=["RELIANCE"])
    s.set_parameters({"ok": 1, "bad": object()})
    assert s.get_parameters() == {"ok": 1}
