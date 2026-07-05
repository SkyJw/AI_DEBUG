"""Log-modelling domain package.

A self-contained, one-way-dependency layer that turns raw board log files into
flat, line-ordered records — no interpretation (no boot segmentation / stage
inference), no textual import. Pipeline::

    raw file text  ->  TargetSet (optional, YAML-driven)  ->  LogFile.parse
                                                            -> list[LogRecord]

Extension slot: one module per log type registers a ``LogFile`` subclass via
``@register_log`` at import time. Import new log-type modules here so their
registration runs — explicit and greppable, like ``agents`` / ``tools``.
"""

from aidbg.logs import cbblog, panic, uboot  # noqa: F401  (import side effect: registration)
from aidbg.logs.base import LOG_TYPES, LogFile, log_type, register_log
from aidbg.logs.bundle import (
    Bundle,
    BundleKind,
    Evidence,
    load_evidence,
    parse_bundle_name,
)
from aidbg.logs.config import (
    LogConfigSet,
    LogRoute,
    LogTypeConfig,
    load_log_configs,
)
from aidbg.logs.problems import (
    Problem,
    ProblemCatalog,
    check_links,
    load_problems,
)
from aidbg.logs.records import (
    CbblogRecord,
    LogRecord,
    LogTimestamp,
    PanicRecord,
    UbootRecord,
)
from aidbg.logs.target import Target, TargetSet

__all__ = [
    # records
    "LogRecord",
    "LogTimestamp",
    "UbootRecord",
    "PanicRecord",
    "CbblogRecord",
    # target
    "Target",
    "TargetSet",
    # problems
    "Problem",
    "ProblemCatalog",
    "load_problems",
    "check_links",
    # base + registry
    "LogFile",
    "LOG_TYPES",
    "register_log",
    "log_type",
    # config
    "LogConfigSet",
    "LogTypeConfig",
    "LogRoute",
    "load_log_configs",
    # bundle
    "Bundle",
    "BundleKind",
    "Evidence",
    "load_evidence",
    "parse_bundle_name",
]
