# Contains semi-automatically generated non-complete model of config format.
# Please refer to documentation to define a full model

from __future__ import annotations
from pydantic.dataclasses import dataclass
from dataclasses import field
from typing import Optional


@dataclass
class Telemetry:
    progress: Progress


@dataclass
class Progress:
    enabled: bool
    logBest: int
    logPopulation: int
    dumpPopulation: bool


def _default_telemetry() -> Telemetry:
    return Telemetry(
        progress=Progress(
            enabled=True, logBest=100, logPopulation=1000, dumpPopulation=False
        )
    )


@dataclass
class Config:
    termination: Termination
    telemetry: Optional[Telemetry] = field(default_factory=_default_telemetry)
    environment: Optional[Environment] = None


@dataclass
class Termination:
    maxTime: Optional[int] = None
    maxGenerations: Optional[int] = None


@dataclass
class Logging:
    enabled: bool


def _default_logging() -> Logging:
    return Logging(enabled=True)


@dataclass
class Environment:
    logging: Logging = field(default_factory=_default_logging)
    isExperimental: Optional[bool] = None
