"""Declarative cross-sectional pipeline container."""

from __future__ import annotations

from typing import ClassVar, Dict, List, Optional, Tuple

from .factor import Factor
from .filter import Filter

UNIVERSE_ATTR = "universe"


class Pipeline:
    """Base class for declarative cross-sectional pipelines.

    Subclasses declare ``Factor`` / ``Filter`` class attributes. The optional
    ``universe`` attribute defines a root mask; every other column is computed
    only on symbols that pass the universe filter.
    """

    __pipeline_columns__: Tuple[Tuple[str, Factor], ...] = ()
    __pipeline_universe__: Optional[Filter] = None

    refresh_universe_every: ClassVar[Optional[int]] = None

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)

        columns: List[Tuple[str, Factor]] = []
        universe: Optional[Filter] = None
        seen: set = set()

        for klass in cls.__mro__:
            if klass in (Pipeline, object):
                continue
            for name, value in vars(klass).items():
                if name.startswith("_") or name in seen:
                    continue
                if not isinstance(value, Factor):
                    continue
                seen.add(name)
                if name == UNIVERSE_ATTR:
                    if not isinstance(value, Filter):
                        raise TypeError(
                            f"{cls.__name__}.universe must be a Filter, "
                            f"got {type(value).__name__}"
                        )
                    universe = value
                else:
                    columns.append((name, value))

        if not columns:
            raise TypeError(
                f"Pipeline subclass {cls.__name__} declares no factor columns."
            )

        cls.__pipeline_columns__ = tuple(columns)
        cls.__pipeline_universe__ = universe

    @classmethod
    def get_columns(cls) -> Dict[str, Factor]:
        return dict(cls.__pipeline_columns__)

    @classmethod
    def get_universe(cls) -> Optional[Filter]:
        return cls.__pipeline_universe__

    @classmethod
    def required_columns(cls) -> List[str]:
        cols: List[str] = []
        for _, factor in cls.__pipeline_columns__:
            for c in factor.required_columns():
                if c not in cols:
                    cols.append(c)
        if cls.__pipeline_universe__ is not None:
            for c in cls.__pipeline_universe__.required_columns():
                if c not in cols:
                    cols.append(c)
        return cols

    @classmethod
    def required_window(cls) -> int:
        window = 1
        for _, factor in cls.__pipeline_columns__:
            window = max(window, factor.required_window())
        if cls.__pipeline_universe__ is not None:
            window = max(window, cls.__pipeline_universe__.required_window())
        return window
