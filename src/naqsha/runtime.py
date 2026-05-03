"""
V1 backward compatibility shim.

This module re-exports from naqsha.core.runtime for backward compatibility.
New code should import from naqsha.core.runtime directly.
"""

from naqsha.core.runtime import CoreRuntime, RunResult, RuntimeConfig

__all__ = ["CoreRuntime", "RunResult", "RuntimeConfig"]
