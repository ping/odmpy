class OdmpyRuntimeError(RuntimeError):
    pass


class LibbyNotConfiguredError(OdmpyRuntimeError):
    """
    Raised when Libby is not yet configured. Used in `--check`.
    """

    pass
