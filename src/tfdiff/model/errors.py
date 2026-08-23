# an error message lists at most this many validation problems
SHOWN_ERRORS = 5


class TfDiffError(Exception):
    """Base of every error the CLI maps to an exit code.

    Messages name addresses and attribute paths, never values: a value may be a secret.
    """


class InputError(TfDiffError):
    """The plan JSON is missing, malformed, too large or inconsistent."""


class CompatibilityError(InputError):
    """The plan comes from a Terraform JSON format this version does not understand."""


class ConfigError(TfDiffError):
    """The configuration file, environment or flags are invalid."""
