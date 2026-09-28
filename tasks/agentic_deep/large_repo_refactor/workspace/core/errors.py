"""Application exceptions."""


class AppError(Exception):
    """Base class for deliberate application errors."""


class NotFound(AppError):
    def __init__(self, kind: str, key: str) -> None:
        self.kind, self.key = kind, key
        super().__init__(f"{kind} not found: {key}")


class ValidationError(AppError):
    pass


class InsufficientStock(AppError):
    def __init__(self, sku: str, requested: int, available: int) -> None:
        self.sku, self.requested, self.available = sku, requested, available
        super().__init__(f"insufficient stock for {sku}: requested {requested}, available {available}")


class PaymentDeclined(AppError):
    def __init__(self, order_id: str, reason: str) -> None:
        self.order_id, self.reason = order_id, reason
        super().__init__(f"payment for {order_id} declined: {reason}")


class InvalidTransition(AppError):
    def __init__(self, kind: str, key: str, current: str, wanted: str) -> None:
        super().__init__(f"{kind} {key} cannot go from {current} to {wanted}")
