"""Exit-code-bearing exceptions shared by every command: 1 findings, 2 a refusal."""


class StayfixedError(Exception):
    """Base class; never raised directly."""


class Failure(StayfixedError):
    """Findings or a failed operation: exit code 1."""


class Refusal(StayfixedError):
    """A refusal or an internal error a caller must never read as permission: exit code 2."""
