"""Exceptions raised by the ledger package."""


class LedgerError(Exception):
    """Base class for every deliberate error in this package."""


class ValidationError(LedgerError):
    """Malformed input (bad amount, bad date, empty memo...)."""


class UnknownAccountError(LedgerError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"unknown account: {code}")


class DuplicateAccountError(LedgerError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"account already exists: {code}")


class UnbalancedTransactionError(LedgerError):
    def __init__(self, difference) -> None:
        self.difference = difference
        super().__init__(f"transaction does not balance (off by {difference})")
