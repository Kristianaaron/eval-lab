#!/usr/bin/env python3
"""Generate the ``agentic.large_repo_refactor.001`` workspace (and its reference solution).

The workspace is a small but wide e-commerce back-end: ``core/`` (models, registry,
clock, ids, settings and the event system), ``services/`` (orders, inventory,
payments, shipping, ...), ``plugins/`` (fifteen event subscribers) and ``cli/``.
Every module is emitted from the same template in one of two modes:

* **legacy** (default): the module-global ``core.events.emit(name, payload)`` /
  ``core.events.on(name, handler)`` API with positional string event names, used at
  roughly sixty call sites spread over ~30 modules, with deliberately varied import
  styles (``from core import events``, ``from core.events import emit``,
  ``import core.events as ev``, string constants from ``core.constants``).
* **reference** (``--reference``): the typed ``EventBus`` / ``Event`` / ``EventType``
  API the task prompt specifies, with the bus injected through ``build_app``.

Only the standard library is used and the output is fully deterministic for a given
``--seed`` (the seed picks import styles and the order plugins are registered in).

    .venv/bin/python scripts/gen_large_repo_refactor.py              # writes the workspace
    .venv/bin/python scripts/gen_large_repo_refactor.py --reference  # writes the overlay
    .venv/bin/python scripts/gen_large_repo_refactor.py --check      # call-site statistics

The generator itself needs Python 3.12 (nested f-string quotes); the code it emits
runs on Python 3.11+.
"""

from __future__ import annotations

import argparse
import random
import shutil
import sys
from pathlib import Path

if sys.version_info < (3, 12):  # the templates use PEP 701 f-strings
    sys.exit("gen_large_repo_refactor.py needs Python 3.12+ (use .venv/bin/python)")

REPO_ROOT = Path(__file__).resolve().parent.parent
TASK_ID = "agentic.large_repo_refactor.001"
DEFAULT_WORKSPACE = REPO_ROOT / "tasks" / "agentic_deep" / "large_repo_refactor" / "workspace"
DEFAULT_REFERENCE = REPO_ROOT / "tests" / "fixtures" / "reference_solutions" / TASK_ID

# name -> (EventType member, payload keys); order matters (it is the enum order).
EVENTS: list[tuple[str, str]] = [
    ("customer.registered", "CUSTOMER_REGISTERED"),
    ("customer.upgraded", "CUSTOMER_UPGRADED"),
    ("cart.item_added", "CART_ITEM_ADDED"),
    ("order.created", "ORDER_CREATED"),
    ("order.paid", "ORDER_PAID"),
    ("order.cancelled", "ORDER_CANCELLED"),
    ("order.shipped", "ORDER_SHIPPED"),
    ("inventory.reserved", "INVENTORY_RESERVED"),
    ("inventory.released", "INVENTORY_RELEASED"),
    ("inventory.low", "INVENTORY_LOW"),
    ("payment.captured", "PAYMENT_CAPTURED"),
    ("payment.failed", "PAYMENT_FAILED"),
    ("payment.refunded", "PAYMENT_REFUNDED"),
    ("shipment.dispatched", "SHIPMENT_DISPATCHED"),
    ("shipment.delivered", "SHIPMENT_DELIVERED"),
    ("notification.sent", "NOTIFICATION_SENT"),
]
MEMBER_OF = dict(EVENTS)
CONST_OF = {name: "EVENT_" + member for name, member in EVENTS}

PLUGINS = [
    "audit",
    "metrics",
    "email_notifier",
    "sms_notifier",
    "stock_guard",
    "fraud_check",
    "loyalty",
    "webhooks",
    "reporting",
    "analytics",
    "cache_invalidator",
    "search_indexer",
    "slack_alerts",
    "warehouse_sync",
    "ops_dashboard",
]


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------


class Api:
    """Renders event calls in either the legacy or the new style for one module."""

    def __init__(self, legacy: bool, style: str) -> None:
        self.legacy = legacy
        self.style = style  # module | names | alias | const

    # -- imports -------------------------------------------------------------
    def imports(self, *, emits: list[str] = (), subscribes: list[str] = ()) -> str:
        if not self.legacy:
            return "from core.events import Event, EventType\n"
        if self.style == "module":
            return "from core import events\n"
        if self.style == "alias":
            return "import core.events as ev\n"
        if self.style == "names":
            funcs = []
            if emits:
                funcs.append("emit")
            if subscribes:
                funcs.append("on")
            return f"from core.events import {', '.join(funcs) or 'emit'}\n"
        # const style: module import plus the string constants it uses
        consts = sorted({CONST_OF[n] for n in (*emits, *subscribes)})
        lines = "from core import events\n"
        if consts:
            lines += "from core.constants import " + ", ".join(consts) + "\n"
        return lines

    # -- call sites ----------------------------------------------------------
    def name_expr(self, name: str) -> str:
        if not self.legacy:
            return f"EventType.{MEMBER_OF[name]}"
        if self.style == "const":
            return CONST_OF[name]
        return f'"{name}"'

    def _fn(self, legacy_name: str) -> str:
        if self.style == "alias":
            return f"ev.{legacy_name}"
        if self.style == "names":
            return legacy_name
        return f"events.{legacy_name}"

    def emit(self, bus: str, name: str, payload: str, *, expr: str | None = None) -> str:
        name_expr = expr or self.name_expr(name)
        if not self.legacy:
            return f"{bus}.publish(Event({name_expr}, {payload}))"
        return f"{self._fn('emit')}({name_expr}, {payload})"

    def on(self, bus: str, name: str, handler: str, *, expr: str | None = None) -> str:
        name_expr = expr or self.name_expr(name)
        if not self.legacy:
            return f"{bus}.subscribe({name_expr}, {handler})"
        return f"{self._fn('on')}({name_expr}, {handler})"

    def handler(self, indent: str, fn: str, *, method: bool = True) -> str:
        """The ``def`` line plus a ``payload`` binding line for a handler."""
        self_arg = "self, " if method else ""
        if self.legacy:
            return f"{indent}def {fn}({self_arg}payload: dict) -> None:\n"
        return f"{indent}def {fn}({self_arg}event: Event) -> None:\n{indent}    payload = event.payload\n"


def L(api: Api, legacy_text: str, new_text: str) -> str:
    return legacy_text if api.legacy else new_text


# ---------------------------------------------------------------------------
# core/
# ---------------------------------------------------------------------------


def core_init() -> str:
    return '"""Core building blocks shared by services, plugins and the CLI."""\n'


def core_events(legacy: bool) -> str:
    if legacy:
        return '''"""Process-wide event dispatch (legacy string-keyed API).

Handlers are registered per event *name* and receive the payload dict. The
registry is a module global, which is why ``build_app`` has to ``reset()`` it:
two applications cannot coexist in one process.
"""

from __future__ import annotations

from typing import Callable

Handler = Callable[[dict], None]

_HANDLERS: dict[str, list[Handler]] = {}


def on(name: str, handler: Handler) -> None:
    """Register ``handler`` for the event called ``name``."""
    if not isinstance(name, str) or not name:
        raise TypeError("event name must be a non-empty string")
    handlers = _HANDLERS.setdefault(name, [])
    if handler not in handlers:
        handlers.append(handler)


def off(name: str, handler: Handler) -> None:
    handlers = _HANDLERS.get(name, [])
    if handler in handlers:
        handlers.remove(handler)


def emit(name: str, payload: dict | None = None) -> int:
    """Call every handler registered for ``name``; returns how many ran."""
    if not isinstance(name, str) or not name:
        raise TypeError("event name must be a non-empty string")
    data = dict(payload or {})
    handlers = list(_HANDLERS.get(name, []))
    for handler in handlers:
        handler(data)
    return len(handlers)


def handler_count(name: str) -> int:
    return len(_HANDLERS.get(name, []))


def reset() -> None:
    """Forget every handler (used when a new application is built)."""
    _HANDLERS.clear()
'''
    members = "\n".join(f'    {member} = "{name}"' for name, member in EVENTS)
    return f'''"""Typed, instance-based event dispatch.

An :class:`EventBus` holds its own subscriptions, so several applications can
coexist in one process. Events are :class:`Event` records whose ``type`` is a
member of :class:`EventType`; handlers receive the whole event.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class EventType(Enum):
{members}


@dataclass(frozen=True)
class Event:
    type: EventType
    payload: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.type, EventType):
            raise TypeError(f"event type must be an EventType, got {{self.type!r}}")


Handler = Callable[[Event], None]


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[EventType, list[Handler]] = {{}}

    def subscribe(self, event_type: EventType, handler: Handler) -> None:
        if not isinstance(event_type, EventType):
            raise TypeError(f"expected an EventType, got {{event_type!r}}")
        handlers = self._handlers.setdefault(event_type, [])
        if handler not in handlers:
            handlers.append(handler)

    def unsubscribe(self, event_type: EventType, handler: Handler) -> None:
        if not isinstance(event_type, EventType):
            raise TypeError(f"expected an EventType, got {{event_type!r}}")
        handlers = self._handlers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)

    def publish(self, event: Event) -> int:
        if not isinstance(event, Event):
            raise TypeError(f"expected an Event, got {{event!r}}")
        handlers = tuple(self._handlers.get(event.type, ()))
        for handler in handlers:
            handler(event)
        return len(handlers)

    def handlers(self, event_type: EventType) -> tuple[Handler, ...]:
        if not isinstance(event_type, EventType):
            raise TypeError(f"expected an EventType, got {{event_type!r}}")
        return tuple(self._handlers.get(event_type, ()))

    def clear(self) -> None:
        self._handlers.clear()


_default_bus: EventBus | None = None


def default_bus() -> EventBus:
    """A lazily created process-wide bus for code that has no injected bus."""
    global _default_bus
    if _default_bus is None:
        _default_bus = EventBus()
    return _default_bus


def reset_default_bus() -> None:
    global _default_bus
    _default_bus = None
'''


def core_constants(legacy: bool) -> str:
    head = '''"""Shared constants."""

DEFAULT_CURRENCY = "USD"
MAX_LINES_PER_ORDER = 25
SUPPORTED_CARRIERS = ("ups", "dhl", "fedex")
NOTIFICATION_CHANNELS = ("email", "sms", "ops", "slack")
'''
    if not legacy:
        return head
    consts = "\n".join(f'{CONST_OF[name]} = "{name}"' for name, _ in EVENTS)
    all_events = ",\n".join(f"    {CONST_OF[name]}" for name, _ in EVENTS)
    return head + f"\n# Event names understood by core.events (see plugins/audit.py).\n{consts}\n\nALL_EVENTS = (\n{all_events},\n)\n"


def core_errors() -> str:
    return '''"""Application exceptions."""


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
'''


def core_models() -> str:
    return '''"""Plain records stored in the registries."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Customer:
    id: str
    email: str
    name: str
    tier: str = "standard"


@dataclass(frozen=True)
class Product:
    sku: str
    name: str
    price_cents: int


@dataclass(frozen=True)
class OrderLine:
    sku: str
    quantity: int
    unit_price_cents: int

    @property
    def total_cents(self) -> int:
        return self.quantity * self.unit_price_cents


@dataclass
class Order:
    id: str
    customer_id: str
    lines: tuple[OrderLine, ...]
    total_cents: int
    status: str = "created"
    created_at: int = 0
    history: list[str] = field(default_factory=list)

    def line_summary(self) -> list[tuple[str, int]]:
        return [(line.sku, line.quantity) for line in self.lines]


@dataclass
class Payment:
    id: str
    order_id: str
    amount_cents: int
    status: str = "captured"


@dataclass
class Shipment:
    id: str
    order_id: str
    carrier: str
    status: str = "dispatched"
'''


def core_clock() -> str:
    return '''"""A deterministic clock: every call to ``now()`` advances by one tick."""

from __future__ import annotations


class Clock:
    def __init__(self, start: int = 1_700_000_000) -> None:
        self._now = start

    def now(self) -> int:
        self._now += 1
        return self._now

    def peek(self) -> int:
        return self._now
'''


def core_ids() -> str:
    return '''"""Sequential, human-readable identifiers such as ``ord-0001``."""

from __future__ import annotations


class IdGenerator:
    def __init__(self, prefix: str, width: int = 4) -> None:
        self.prefix = prefix
        self.width = width
        self._counter = 0

    def next(self) -> str:
        self._counter += 1
        return f"{self.prefix}-{self._counter:0{self.width}d}"

    @property
    def issued(self) -> int:
        return self._counter
'''


def core_registry() -> str:
    return '''"""A tiny in-memory table keyed by string id."""

from __future__ import annotations

from typing import Callable, Generic, Iterator, TypeVar

from core.errors import NotFound, ValidationError

T = TypeVar("T")


class Registry(Generic[T]):
    def __init__(self, kind: str, key: Callable[[T], str]) -> None:
        self.kind = kind
        self._key = key
        self._rows: dict[str, T] = {}

    def add(self, row: T) -> T:
        key = self._key(row)
        if key in self._rows:
            raise ValidationError(f"{self.kind} already exists: {key}")
        self._rows[key] = row
        return row

    def get(self, key: str) -> T:
        try:
            return self._rows[key]
        except KeyError:
            raise NotFound(self.kind, key) from None

    def has(self, key: str) -> bool:
        return key in self._rows

    def all(self) -> list[T]:
        return list(self._rows.values())

    def __len__(self) -> int:
        return len(self._rows)

    def __iter__(self) -> Iterator[T]:
        return iter(self._rows.values())
'''


def core_config(rng: random.Random) -> str:
    return f'''"""Runtime settings with sensible defaults for tests and the demo."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    low_stock_threshold: int = {rng.choice([3, 4, 5])}
    loyalty_points_per_dollar: int = {rng.choice([1, 2])}
    gold_discount_percent: int = {rng.choice([5, 10])}
    fraud_limit_cents: int = {rng.choice([50_000, 75_000, 100_000])}
    free_shipping_threshold_cents: int = {rng.choice([5_000, 7_500])}
    webhook_url: str = "https://hooks.example.test/orders"
    ops_channel: str = "#ops"


DEFAULT_SETTINGS = Settings()
'''


# ---------------------------------------------------------------------------
# services/
# ---------------------------------------------------------------------------


def services_init() -> str:
    return '''"""Application services. Each one takes its collaborators explicitly."""

from __future__ import annotations

from dataclasses import dataclass

from services.carts import CartService
from services.catalog import CatalogService
from services.customers import CustomerService
from services.inventory import InventoryService
from services.notifications import NotificationService
from services.orders import OrderService
from services.payments import PaymentService
from services.pricing import PricingService
from services.returns import ReturnsService
from services.shipping import ShippingService


@dataclass
class Services:
    customers: CustomerService
    catalog: CatalogService
    inventory: InventoryService
    pricing: PricingService
    carts: CartService
    orders: OrderService
    payments: PaymentService
    shipping: ShippingService
    returns: ReturnsService
    notifications: NotificationService

    def __iter__(self):
        return iter(
            (
                self.customers,
                self.catalog,
                self.inventory,
                self.pricing,
                self.carts,
                self.orders,
                self.payments,
                self.shipping,
                self.returns,
                self.notifications,
            )
        )
'''


def service_customers(api: Api) -> str:
    bus = "self.bus"
    return f'''"""Customer registration and tier upgrades."""

from __future__ import annotations

{api.imports(emits=["customer.registered", "customer.upgraded"])}from core.errors import ValidationError
from core.ids import IdGenerator
from core.models import Customer
from core.registry import Registry

TIERS = ("standard", "silver", "gold")


class CustomerService:
    def __init__(self, {L(api, "", "bus, ")}customers: Registry[Customer], ids: IdGenerator) -> None:
{L(api, "", "        self.bus = bus\n")}        self.customers = customers
        self.ids = ids

    def register(self, email: str, name: str) -> Customer:
        if "@" not in email:
            raise ValidationError(f"invalid email: {{email}}")
        if any(c.email == email for c in self.customers):
            raise ValidationError(f"email already registered: {{email}}")
        customer = self.customers.add(Customer(id=self.ids.next(), email=email, name=name))
        {api.emit(bus, "customer.registered", '{"customer_id": customer.id, "email": email, "name": name}')}
        return customer

    def upgrade(self, customer_id: str, tier: str) -> Customer:
        if tier not in TIERS:
            raise ValidationError(f"unknown tier: {{tier}}")
        customer = self.customers.get(customer_id)
        previous = customer.tier
        customer.tier = tier
        {api.emit(bus, "customer.upgraded", '{"customer_id": customer.id, "tier": tier, "previous": previous}')}
        return customer

    def get(self, customer_id: str) -> Customer:
        return self.customers.get(customer_id)
'''


def service_catalog(api: Api) -> str:
    return f'''"""Product catalogue."""

from __future__ import annotations

from core.errors import ValidationError
from core.models import Product
from core.registry import Registry


class CatalogService:
    def __init__(self, {L(api, "", "bus, ")}products: Registry[Product]) -> None:
{L(api, "", "        self.bus = bus\n")}        self.products = products

    def add_product(self, sku: str, name: str, price_cents: int) -> Product:
        if price_cents <= 0:
            raise ValidationError("price must be positive")
        return self.products.add(Product(sku=sku, name=name, price_cents=price_cents))

    def get(self, sku: str) -> Product:
        return self.products.get(sku)

    def skus(self) -> list[str]:
        return sorted(p.sku for p in self.products)
'''


def service_inventory(api: Api) -> str:
    bus = "self.bus"
    return f'''"""Stock levels and reservations."""

from __future__ import annotations

{api.imports(emits=["inventory.reserved", "inventory.released", "inventory.low"])}from core.config import Settings
from core.errors import InsufficientStock, ValidationError
from core.models import OrderLine


class InventoryService:
    def __init__(self, {L(api, "", "bus, ")}settings: Settings) -> None:
{L(api, "", "        self.bus = bus\n")}        self.settings = settings
        self.stock: dict[str, int] = {{}}
        self.reservations: dict[str, list[tuple[str, int]]] = {{}}

    def receive(self, sku: str, quantity: int) -> int:
        if quantity <= 0:
            raise ValidationError("received quantity must be positive")
        self.stock[sku] = self.stock.get(sku, 0) + quantity
        return self.stock[sku]

    def available(self, sku: str) -> int:
        return self.stock.get(sku, 0)

    def reserve(self, order_id: str, lines: tuple[OrderLine, ...]) -> None:
        for line in lines:
            available = self.available(line.sku)
            if line.quantity > available:
                raise InsufficientStock(line.sku, line.quantity, available)
        summary = []
        for line in lines:
            self.stock[line.sku] -= line.quantity
            summary.append((line.sku, line.quantity))
        self.reservations[order_id] = summary
        {api.emit(bus, "inventory.reserved", '{"order_id": order_id, "lines": list(summary)}')}
        for sku, _ in summary:
            remaining = self.stock[sku]
            if remaining <= self.settings.low_stock_threshold:
                {api.emit(bus, "inventory.low", '{"sku": sku, "remaining": remaining, "threshold": self.settings.low_stock_threshold}')}

    def release(self, order_id: str) -> list[tuple[str, int]]:
        summary = self.reservations.pop(order_id, [])
        for sku, quantity in summary:
            self.stock[sku] = self.stock.get(sku, 0) + quantity
        if summary:
            {api.emit(bus, "inventory.released", '{"order_id": order_id, "lines": list(summary)}')}
        return summary
'''


def service_pricing(api: Api) -> str:
    return f'''"""Order totals, including tier discounts."""

from __future__ import annotations

from core.config import Settings
from core.models import OrderLine


class PricingService:
    def __init__(self, {L(api, "", "bus, ")}settings: Settings) -> None:
{L(api, "", "        self.bus = bus\n")}        self.settings = settings

    def subtotal(self, lines: tuple[OrderLine, ...]) -> int:
        return sum(line.total_cents for line in lines)

    def total(self, lines: tuple[OrderLine, ...], tier: str) -> int:
        amount = self.subtotal(lines)
        if tier == "gold":
            amount -= amount * self.settings.gold_discount_percent // 100
        return amount

    def shipping_fee(self, total_cents: int) -> int:
        return 0 if total_cents >= self.settings.free_shipping_threshold_cents else 599
'''


def service_carts(api: Api) -> str:
    bus = "self.bus"
    return f'''"""Per-customer shopping carts."""

from __future__ import annotations

{api.imports(emits=["cart.item_added"])}from core.constants import MAX_LINES_PER_ORDER
from core.errors import ValidationError
from core.models import OrderLine
from services.catalog import CatalogService


class CartService:
    def __init__(self, {L(api, "", "bus, ")}catalog: CatalogService) -> None:
{L(api, "", "        self.bus = bus\n")}        self.catalog = catalog
        self._carts: dict[str, dict[str, int]] = {{}}

    def add_item(self, customer_id: str, sku: str, quantity: int = 1) -> int:
        if quantity <= 0:
            raise ValidationError("quantity must be positive")
        product = self.catalog.get(sku)
        cart = self._carts.setdefault(customer_id, {{}})
        if sku not in cart and len(cart) >= MAX_LINES_PER_ORDER:
            raise ValidationError("too many distinct items in cart")
        cart[sku] = cart.get(sku, 0) + quantity
        {api.emit(bus, "cart.item_added", '{"customer_id": customer_id, "sku": product.sku, "quantity": quantity, "in_cart": cart[sku]}')}
        return cart[sku]

    def lines(self, customer_id: str) -> tuple[OrderLine, ...]:
        cart = self._carts.get(customer_id, {{}})
        return tuple(
            OrderLine(sku=sku, quantity=qty, unit_price_cents=self.catalog.get(sku).price_cents)
            for sku, qty in sorted(cart.items())
        )

    def clear(self, customer_id: str) -> None:
        self._carts.pop(customer_id, None)
'''


def service_orders(api: Api) -> str:
    bus = "self.bus"
    return f'''"""Order lifecycle: created -> paid -> shipped, or cancelled."""

from __future__ import annotations

{api.imports(emits=["order.created", "order.paid", "order.cancelled", "order.shipped"])}from core.clock import Clock
from core.errors import InvalidTransition, ValidationError
from core.ids import IdGenerator
from core.models import Order
from core.registry import Registry
from services.carts import CartService
from services.customers import CustomerService
from services.inventory import InventoryService
from services.pricing import PricingService


class OrderService:
    def __init__(
        self,
        {L(api, "", "bus,\n        ")}orders: Registry[Order],
        ids: IdGenerator,
        clock: Clock,
        carts: CartService,
        pricing: PricingService,
        inventory: InventoryService,
        customers: CustomerService,
    ) -> None:
{L(api, "", "        self.bus = bus\n")}        self.orders = orders
        self.ids = ids
        self.clock = clock
        self.carts = carts
        self.pricing = pricing
        self.inventory = inventory
        self.customers = customers

    def create_order(self, customer_id: str) -> Order:
        customer = self.customers.get(customer_id)
        lines = self.carts.lines(customer_id)
        if not lines:
            raise ValidationError("cart is empty")
        order = Order(
            id=self.ids.next(),
            customer_id=customer.id,
            lines=lines,
            total_cents=self.pricing.total(lines, customer.tier),
            created_at=self.clock.now(),
        )
        self.inventory.reserve(order.id, lines)
        self.orders.add(order)
        self.carts.clear(customer_id)
        order.history.append("created")
        {api.emit(bus, "order.created", '{"order_id": order.id, "customer_id": customer.id, "total_cents": order.total_cents, "lines": order.line_summary()}')}
        return order

    def get(self, order_id: str) -> Order:
        return self.orders.get(order_id)

    def mark_paid(self, order_id: str) -> Order:
        order = self._transition(order_id, {{"created"}}, "paid")
        {api.emit(bus, "order.paid", '{"order_id": order.id, "customer_id": order.customer_id, "total_cents": order.total_cents}')}
        return order

    def mark_shipped(self, order_id: str, shipment_id: str) -> Order:
        order = self._transition(order_id, {{"paid"}}, "shipped")
        {api.emit(bus, "order.shipped", '{"order_id": order.id, "shipment_id": shipment_id}')}
        return order

    def cancel(self, order_id: str, reason: str) -> Order:
        order = self._transition(order_id, {{"created", "paid"}}, "cancelled")
        self.inventory.release(order.id)
        {api.emit(bus, "order.cancelled", '{"order_id": order.id, "customer_id": order.customer_id, "reason": reason}')}
        return order

    def _transition(self, order_id: str, allowed: set[str], target: str) -> Order:
        order = self.orders.get(order_id)
        if order.status not in allowed:
            raise InvalidTransition("order", order.id, order.status, target)
        order.status = target
        order.history.append(target)
        return order
'''


def service_payments(api: Api) -> str:
    bus = "self.bus"
    return f'''"""Card payments (a fake gateway: card ``0000`` is always declined)."""

from __future__ import annotations

{api.imports(emits=["payment.captured", "payment.failed", "payment.refunded"])}from core.errors import PaymentDeclined, ValidationError
from core.ids import IdGenerator
from core.models import Payment
from core.registry import Registry
from services.orders import OrderService

DECLINED_CARD = "0000"


class PaymentService:
    def __init__(self, {L(api, "", "bus, ")}payments: Registry[Payment], ids: IdGenerator, orders: OrderService) -> None:
{L(api, "", "        self.bus = bus\n")}        self.payments = payments
        self.ids = ids
        self.orders = orders

    def capture(self, order_id: str, card_last4: str) -> Payment:
        order = self.orders.get(order_id)
        if order.status != "created":
            raise ValidationError(f"order {{order.id}} is {{order.status}}, cannot capture")
        if card_last4 == DECLINED_CARD:
            {api.emit(bus, "payment.failed", '{"order_id": order.id, "amount_cents": order.total_cents, "reason": "card declined"}')}
            raise PaymentDeclined(order.id, "card declined")
        payment = self.payments.add(Payment(id=self.ids.next(), order_id=order.id, amount_cents=order.total_cents))
        {api.emit(bus, "payment.captured", '{"payment_id": payment.id, "order_id": order.id, "amount_cents": payment.amount_cents}')}
        self.orders.mark_paid(order.id)
        return payment

    def refund(self, payment_id: str) -> Payment:
        payment = self.payments.get(payment_id)
        if payment.status != "captured":
            raise ValidationError(f"payment {{payment.id}} is {{payment.status}}, cannot refund")
        payment.status = "refunded"
        {api.emit(bus, "payment.refunded", '{"payment_id": payment.id, "order_id": payment.order_id, "amount_cents": payment.amount_cents}')}
        return payment

    def for_order(self, order_id: str) -> list[Payment]:
        return [p for p in self.payments if p.order_id == order_id]
'''


def service_shipping(api: Api) -> str:
    bus = "self.bus"
    return f'''"""Shipments."""

from __future__ import annotations

{api.imports(emits=["shipment.dispatched", "shipment.delivered"])}from core.constants import SUPPORTED_CARRIERS
from core.errors import InvalidTransition, ValidationError
from core.ids import IdGenerator
from core.models import Shipment
from core.registry import Registry
from services.orders import OrderService


class ShippingService:
    def __init__(self, {L(api, "", "bus, ")}shipments: Registry[Shipment], ids: IdGenerator, orders: OrderService) -> None:
{L(api, "", "        self.bus = bus\n")}        self.shipments = shipments
        self.ids = ids
        self.orders = orders

    def dispatch(self, order_id: str, carrier: str) -> Shipment:
        if carrier not in SUPPORTED_CARRIERS:
            raise ValidationError(f"unsupported carrier: {{carrier}}")
        order = self.orders.get(order_id)
        if order.status != "paid":
            raise InvalidTransition("order", order.id, order.status, "shipped")
        shipment = self.shipments.add(Shipment(id=self.ids.next(), order_id=order.id, carrier=carrier))
        {api.emit(bus, "shipment.dispatched", '{"shipment_id": shipment.id, "order_id": order.id, "carrier": carrier}')}
        self.orders.mark_shipped(order.id, shipment.id)
        return shipment

    def deliver(self, shipment_id: str) -> Shipment:
        shipment = self.shipments.get(shipment_id)
        if shipment.status != "dispatched":
            raise InvalidTransition("shipment", shipment.id, shipment.status, "delivered")
        shipment.status = "delivered"
        {api.emit(bus, "shipment.delivered", '{"shipment_id": shipment.id, "order_id": shipment.order_id}')}
        return shipment
'''


def service_returns(api: Api) -> str:
    return f'''"""Returns: refund the payment and put the stock back."""

from __future__ import annotations

from core.errors import ValidationError
from services.inventory import InventoryService
from services.orders import OrderService
from services.payments import PaymentService


class ReturnsService:
    def __init__(self, {L(api, "", "bus, ")}orders: OrderService, inventory: InventoryService, payments: PaymentService) -> None:
{L(api, "", "        self.bus = bus\n")}        self.orders = orders
        self.inventory = inventory
        self.payments = payments
        self.returned: list[str] = []

    def process_return(self, order_id: str) -> list[str]:
        order = self.orders.get(order_id)
        if order.status != "shipped":
            raise ValidationError(f"order {{order.id}} is {{order.status}}, cannot be returned")
        refunded = []
        for payment in self.payments.for_order(order.id):
            if payment.status == "captured":
                refunded.append(self.payments.refund(payment.id).id)
        order.status = "returned"
        order.history.append("returned")
        for sku, quantity in order.line_summary():
            self.inventory.receive(sku, quantity)
        self.returned.append(order.id)
        return refunded
'''


def service_notifications(api: Api) -> str:
    bus = "self.bus"
    return f'''"""Outbound notifications (collected in an outbox instead of being sent)."""

from __future__ import annotations

{api.imports(emits=["notification.sent"])}from core.constants import NOTIFICATION_CHANNELS
from core.errors import ValidationError


class NotificationService:
    def __init__(self{L(api, "", ", bus")}) -> None:
{L(api, "", "        self.bus = bus\n")}        self.outbox: list[tuple[str, str, str]] = []

    def send(self, channel: str, recipient: str, message: str) -> int:
        if channel not in NOTIFICATION_CHANNELS:
            raise ValidationError(f"unknown channel: {{channel}}")
        self.outbox.append((channel, recipient, message))
        {api.emit(bus, "notification.sent", '{"channel": channel, "recipient": recipient, "message": message}')}
        return len(self.outbox)

    def sent_via(self, channel: str) -> list[str]:
        return [message for ch, _, message in self.outbox if ch == channel]
'''


# ---------------------------------------------------------------------------
# plugins/
# ---------------------------------------------------------------------------


def plugins_init(order: list[str]) -> str:
    modules = ",\n".join(f'    "plugins.{name}"' for name in order)
    return f'''"""Event subscribers. Every module exposes ``register(app)`` returning its plugin object."""

from __future__ import annotations

PLUGIN_MODULES = (
{modules},
)
'''


def plugin_header(api: Api, doc: str, *, emits: list[str] = (), subscribes: list[str] = (), extra: str = "") -> str:
    imports = api.imports(emits=list(emits), subscribes=list(subscribes))
    return f'"""{doc}"""\n\nfrom __future__ import annotations\n\n{imports}{extra}'


def plugin_audit(api: Api) -> str:
    bus = "app.bus"
    if api.legacy:
        imports = api.imports() + "from core.constants import ALL_EVENTS\n"
        # legacy handlers do not know which event they are handling: one closure per name
        loop = (
            "        for name in ALL_EVENTS:\n"
            f"            {api.on(bus, 'order.created', 'self._recorder(name)', expr='name')}\n"
        )
        handler = (
            "    def _recorder(self, name: str):\n"
            "        def record(payload: dict) -> None:\n"
            "            self.entries.append((name, dict(payload)))\n\n"
            "        return record\n"
        )
    else:
        imports = "from core.events import Event, EventType\n"
        loop = f"        for event_type in EventType:\n            {bus}.subscribe(event_type, self._record)\n"
        handler = "    def _record(self, event: Event) -> None:\n        self.entries.append((event.type.value, dict(event.payload)))\n"
    return f'''"""Audit log: records every event that goes through the application."""

from __future__ import annotations

{imports}

class AuditPlugin:
    name = "audit"

    def __init__(self) -> None:
        self.entries: list[tuple[str, dict]] = []

    def register(self, app) -> None:
{loop}
{handler}
    def names(self) -> list[str]:
        return [name for name, _ in self.entries]

    def count(self, name: str) -> int:
        return sum(1 for entry_name, _ in self.entries if entry_name == name)


def register(app):
    plugin = AuditPlugin()
    plugin.register(app)
    return plugin
'''


def simple_plugin(
    api: Api,
    *,
    doc: str,
    cls: str,
    name: str,
    state: list[str],
    subs: list[tuple[str, str, str]],  # (event name, handler fn, handler body lines)
    emits: list[str] = (),
    extra_imports: str = "",
    methods: str = "",
) -> str:
    bus = "app.bus"
    header = plugin_header(api, doc, emits=list(emits), subscribes=[s[0] for s in subs], extra=extra_imports)
    state_lines = "\n".join(f"        {line}" for line in state)
    register_lines = "\n".join(f"        {api.on(bus, ev, 'self.' + fn)}" for ev, fn, _ in subs)
    handlers = ""
    for ev, fn, body in subs:
        handlers += "\n" + api.handler("    ", fn) + "\n".join(f"        {line}" for line in body.splitlines()) + "\n"
    return f'''{header}

class {cls}:
    name = "{name}"

    def __init__(self, app) -> None:
        self.app = app
{state_lines}

    def register(self, app) -> None:
{register_lines}
{handlers}{methods}

def register(app):
    plugin = {cls}(app)
    plugin.register(app)
    return plugin
'''


def plugin_metrics(api: Api) -> str:
    body = 'self.counts["{ev}"] = self.counts.get("{ev}", 0) + 1'
    subs = [
        ("order.created", "_on_created", body.format(ev="order.created")),
        ("order.paid", "_on_paid", body.format(ev="order.paid") + '\nself.revenue_cents += payload["total_cents"]'),
        ("order.cancelled", "_on_cancelled", body.format(ev="order.cancelled")),
        ("payment.failed", "_on_failed", body.format(ev="payment.failed")),
        ("shipment.delivered", "_on_delivered", body.format(ev="shipment.delivered")),
    ]
    return simple_plugin(
        api,
        doc="Counters for the ops dashboard.",
        cls="MetricsPlugin",
        name="metrics",
        state=["self.counts: dict[str, int] = {}", "self.revenue_cents = 0"],
        subs=subs,
        methods="\n    def snapshot(self) -> dict[str, int]:\n        return dict(sorted(self.counts.items()))\n",
    )


def plugin_email_notifier(api: Api) -> str:
    subs = [
        (
            "order.created",
            "_on_order_created",
            'customer = self.app.services.customers.get(payload["customer_id"])\n'
            'self.app.services.notifications.send("email", customer.email, f"Order {payload[\'order_id\']} received")',
        ),
        (
            "shipment.dispatched",
            "_on_dispatched",
            'order = self.app.services.orders.get(payload["order_id"])\n'
            'customer = self.app.services.customers.get(order.customer_id)\n'
            'self.app.services.notifications.send("email", customer.email, f"Order {order.id} shipped via {payload[\'carrier\']}")',
        ),
        (
            "payment.refunded",
            "_on_refunded",
            'order = self.app.services.orders.get(payload["order_id"])\n'
            'customer = self.app.services.customers.get(order.customer_id)\n'
            'self.app.services.notifications.send("email", customer.email, f"Refund of {payload[\'amount_cents\']} cents for {order.id}")',
        ),
    ]
    return simple_plugin(
        api,
        doc="Customer-facing e-mails.",
        cls="EmailNotifierPlugin",
        name="email_notifier",
        state=["self.sent = 0"],
        subs=[(ev, fn, body + "\nself.sent += 1") for ev, fn, body in subs],
    )


def plugin_sms_notifier(api: Api) -> str:
    subs = [
        (
            "shipment.delivered",
            "_on_delivered",
            'order = self.app.services.orders.get(payload["order_id"])\n'
            'customer = self.app.services.customers.get(order.customer_id)\n'
            'self.app.services.notifications.send("sms", customer.email, f"Delivered: {order.id}")',
        ),
        (
            "payment.failed",
            "_on_payment_failed",
            'order = self.app.services.orders.get(payload["order_id"])\n'
            'customer = self.app.services.customers.get(order.customer_id)\n'
            'self.app.services.notifications.send("sms", customer.email, f"Payment for {order.id} failed: {payload[\'reason\']}")',
        ),
    ]
    return simple_plugin(
        api,
        doc="Short text messages for time-sensitive updates.",
        cls="SmsNotifierPlugin",
        name="sms_notifier",
        state=["self.sent = 0"],
        subs=[(ev, fn, body + "\nself.sent += 1") for ev, fn, body in subs],
    )


def plugin_stock_guard(api: Api) -> str:
    subs = [
        (
            "inventory.low",
            "_on_low",
            'self.alerts.append((payload["sku"], payload["remaining"]))\n'
            'self.app.services.notifications.send("ops", self.app.settings.ops_channel, f"Low stock: {payload[\'sku\']} ({payload[\'remaining\']} left)")',
        ),
        (
            "inventory.released",
            "_on_released",
            'for sku, _ in payload["lines"]:\n    self.alerts = [(s, r) for s, r in self.alerts if s != sku]',
        ),
    ]
    return simple_plugin(
        api,
        doc="Raises operational alerts when stock runs low.",
        cls="StockGuardPlugin",
        name="stock_guard",
        state=["self.alerts: list[tuple[str, int]] = []"],
        subs=subs,
    )


def plugin_fraud_check(api: Api) -> str:
    subs = [
        (
            "order.created",
            "_on_order_created",
            'if payload["total_cents"] > self.app.settings.fraud_limit_cents:\n'
            '    self.flagged.append(payload["order_id"])\n'
            '    self.app.services.orders.cancel(payload["order_id"], "fraud review")',
        ),
    ]
    return simple_plugin(
        api,
        doc="Cancels suspiciously large orders for manual review.",
        cls="FraudCheckPlugin",
        name="fraud_check",
        state=["self.flagged: list[str] = []"],
        subs=subs,
    )


def plugin_loyalty(api: Api) -> str:
    subs = [
        (
            "order.paid",
            "_on_paid",
            'earned = payload["total_cents"] // 100 * self.app.settings.loyalty_points_per_dollar\n'
            'self.points[payload["customer_id"]] = self.points.get(payload["customer_id"], 0) + earned',
        ),
        (
            "payment.refunded",
            "_on_refunded",
            'order = self.app.services.orders.get(payload["order_id"])\n'
            'lost = payload["amount_cents"] // 100 * self.app.settings.loyalty_points_per_dollar\n'
            'self.points[order.customer_id] = max(0, self.points.get(order.customer_id, 0) - lost)',
        ),
        (
            "customer.upgraded",
            "_on_upgraded",
            'if payload["tier"] == "gold":\n    self.points[payload["customer_id"]] = self.points.get(payload["customer_id"], 0) + 100',
        ),
    ]
    return simple_plugin(
        api,
        doc="Loyalty points per customer.",
        cls="LoyaltyPlugin",
        name="loyalty",
        state=["self.points: dict[str, int] = {}"],
        subs=subs,
    )


def plugin_webhooks(api: Api) -> str:
    subs = [
        ("order.paid", "_on_paid", 'self.deliveries.append((self.app.settings.webhook_url, "order.paid", dict(payload)))'),
        ("shipment.dispatched", "_on_dispatched", 'self.deliveries.append((self.app.settings.webhook_url, "shipment.dispatched", dict(payload)))'),
        ("order.cancelled", "_on_cancelled", 'self.deliveries.append((self.app.settings.webhook_url, "order.cancelled", dict(payload)))'),
    ]
    return simple_plugin(
        api,
        doc="Outbound webhooks (recorded, not sent).",
        cls="WebhooksPlugin",
        name="webhooks",
        state=["self.deliveries: list[tuple[str, str, dict]] = []"],
        subs=subs,
    )


def plugin_reporting(api: Api) -> str:
    subs = [
        ("shipment.delivered", "_on_delivered", 'self.delivered.append(payload["order_id"])'),
        ("order.cancelled", "_on_cancelled", 'self.cancelled.append((payload["order_id"], payload["reason"]))'),
        ("payment.captured", "_on_captured", 'self.captured_cents += payload["amount_cents"]'),
    ]
    methods = (
        "\n    def summary(self) -> str:\n"
        '        return (\n'
        '            f"delivered={len(self.delivered)} cancelled={len(self.cancelled)} "\n'
        '            f"captured_cents={self.captured_cents}"\n'
        "        )\n"
    )
    return simple_plugin(
        api,
        doc="Numbers for the end-of-day report.",
        cls="ReportingPlugin",
        name="reporting",
        state=["self.delivered: list[str] = []", "self.cancelled: list[tuple[str, str]] = []", "self.captured_cents = 0"],
        subs=subs,
        methods=methods,
    )


def plugin_analytics(api: Api) -> str:
    subs = [
        ("cart.item_added", "_on_item_added", 'self.popular[payload["sku"]] = self.popular.get(payload["sku"], 0) + payload["quantity"]'),
        ("customer.registered", "_on_registered", "self.signups += 1"),
        ("order.created", "_on_order_created", 'self.basket_sizes.append(len(payload["lines"]))'),
    ]
    methods = "\n    def top_sku(self) -> str | None:\n        if not self.popular:\n            return None\n        return max(sorted(self.popular), key=lambda sku: self.popular[sku])\n"
    return simple_plugin(
        api,
        doc="Product analytics.",
        cls="AnalyticsPlugin",
        name="analytics",
        state=["self.popular: dict[str, int] = {}", "self.signups = 0", "self.basket_sizes: list[int] = []"],
        subs=subs,
        methods=methods,
    )


def plugin_cache_invalidator(api: Api) -> str:
    subs = [
        ("customer.upgraded", "_on_upgraded", 'self.invalidated.append(f"customer:{payload[\'customer_id\']}")'),
        ("order.created", "_on_order_created", 'self.invalidated.append(f"orders:{payload[\'customer_id\']}")'),
        ("order.paid", "_on_order_paid", 'self.invalidated.append(f"order:{payload[\'order_id\']}")'),
        ("order.cancelled", "_on_order_cancelled", 'self.invalidated.append(f"order:{payload[\'order_id\']}")'),
        ("order.shipped", "_on_order_shipped", 'self.invalidated.append(f"order:{payload[\'order_id\']}")'),
    ]
    return simple_plugin(
        api,
        doc="Tracks cache keys that must be dropped.",
        cls="CacheInvalidatorPlugin",
        name="cache_invalidator",
        state=["self.invalidated: list[str] = []"],
        subs=subs,
    )


def plugin_search_indexer(api: Api) -> str:
    subs = [
        ("customer.registered", "_on_registered", 'self.index[payload["customer_id"]] = {"name": payload["name"], "email": payload["email"], "tier": "standard"}'),
        ("customer.upgraded", "_on_upgraded", 'entry = self.index.setdefault(payload["customer_id"], {})\nentry["tier"] = payload["tier"]'),
    ]
    methods = "\n    def search(self, text: str) -> list[str]:\n        needle = text.lower()\n        return sorted(cid for cid, doc in self.index.items() if needle in str(doc.get(\"name\", \"\")).lower())\n"
    return simple_plugin(
        api,
        doc="Keeps a searchable customer index up to date.",
        cls="SearchIndexerPlugin",
        name="search_indexer",
        state=["self.index: dict[str, dict] = {}"],
        subs=subs,
        methods=methods,
    )


def plugin_slack_alerts(api: Api) -> str:
    subs = [
        ("payment.failed", "_on_payment_failed", 'self.alerts.append(f"payment failed for {payload[\'order_id\']}: {payload[\'reason\']}")'),
        ("inventory.low", "_on_low", 'self.alerts.append(f"low stock {payload[\'sku\']}={payload[\'remaining\']}")'),
        ("order.cancelled", "_on_cancelled", 'if payload["reason"] == "fraud review":\n    self.alerts.append(f"fraud hold on {payload[\'order_id\']}")'),
    ]
    return simple_plugin(
        api,
        doc="Slack alerts for the on-call channel (recorded, not sent).",
        cls="SlackAlertsPlugin",
        name="slack_alerts",
        state=["self.alerts: list[str] = []"],
        subs=subs,
    )


def plugin_warehouse_sync(api: Api) -> str:
    subs = [
        ("inventory.reserved", "_on_reserved", 'self.pending[payload["order_id"]] = list(payload["lines"])'),
        ("inventory.released", "_on_released", 'self.pending.pop(payload["order_id"], None)'),
        ("shipment.dispatched", "_on_dispatched", 'self.pending.pop(payload["order_id"], None)\nself.shipped.append(payload["order_id"])'),
    ]
    return simple_plugin(
        api,
        doc="Mirrors reservations to the warehouse system.",
        cls="WarehouseSyncPlugin",
        name="warehouse_sync",
        state=["self.pending: dict[str, list] = {}", "self.shipped: list[str] = []"],
        subs=subs,
    )


def plugin_ops_dashboard(api: Api) -> str:
    """A plugin that both subscribes and publishes (chained events)."""
    bus = "app.bus"
    if api.legacy:
        imports = api.imports(emits=["notification.sent"], subscribes=["order.shipped", "notification.sent"])
    else:
        imports = "from core.events import Event, EventType\n"
    return f'''"""Ops dashboard: escalates shipped orders that took too long to leave the building."""

from __future__ import annotations

{imports}

class OpsDashboardPlugin:
    name = "ops_dashboard"

    def __init__(self, app) -> None:
        self.app = app
        self.notifications = 0
        self.escalations: list[str] = []

    def register(self, app) -> None:
        {api.on(bus, "order.shipped", "self._on_shipped")}
        {api.on(bus, "notification.sent", "self._on_notification")}

{api.handler("    ", "_on_shipped")}        order = self.app.services.orders.get(payload["order_id"])
        if order.total_cents >= self.app.settings.free_shipping_threshold_cents:
            self.escalations.append(order.id)
            {api.emit("self.app.bus", "notification.sent", '{"channel": "ops", "recipient": self.app.settings.ops_channel, "message": f"priority shipment {payload[\'shipment_id\']}"}')}

{api.handler("    ", "_on_notification")}        if payload["channel"] == "ops":
            self.notifications += 1


def register(app):
    plugin = OpsDashboardPlugin(app)
    plugin.register(app)
    return plugin
'''


PLUGIN_GENERATORS = {
    "audit": plugin_audit,
    "metrics": plugin_metrics,
    "email_notifier": plugin_email_notifier,
    "sms_notifier": plugin_sms_notifier,
    "stock_guard": plugin_stock_guard,
    "fraud_check": plugin_fraud_check,
    "loyalty": plugin_loyalty,
    "webhooks": plugin_webhooks,
    "reporting": plugin_reporting,
    "analytics": plugin_analytics,
    "cache_invalidator": plugin_cache_invalidator,
    "search_indexer": plugin_search_indexer,
    "slack_alerts": plugin_slack_alerts,
    "warehouse_sync": plugin_warehouse_sync,
    "ops_dashboard": plugin_ops_dashboard,
}


# ---------------------------------------------------------------------------
# app.py and cli/
# ---------------------------------------------------------------------------


def app_module(api: Api) -> str:
    bus_arg = "" if api.legacy else "bus: EventBus | None = None, "
    return f'''"""Application assembly: registries, services and plugins wired together."""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field

{L(api, "from core import events\n", "from core.events import EventBus\n")}from core.clock import Clock
from core.config import DEFAULT_SETTINGS, Settings
from core.ids import IdGenerator
from core.models import Customer, Order, Payment, Product, Shipment
from core.registry import Registry
from plugins import PLUGIN_MODULES
from services import Services
from services.carts import CartService
from services.catalog import CatalogService
from services.customers import CustomerService
from services.inventory import InventoryService
from services.notifications import NotificationService
from services.orders import OrderService
from services.payments import PaymentService
from services.pricing import PricingService
from services.returns import ReturnsService
from services.shipping import ShippingService


@dataclass
class App:
    settings: Settings
    clock: Clock
{L(api, "", "    bus: EventBus\n")}    services: Services | None = None
    plugins: dict[str, object] = field(default_factory=dict)


def build_app({bus_arg}settings: Settings | None = None) -> App:
    """Create a fully wired application{L(api, " (resets the global event registry)", "")}."""
    settings = settings or DEFAULT_SETTINGS
{L(api, "    events.reset()\n", "    bus = bus if bus is not None else EventBus()\n")}    clock = Clock()
    app = App(settings=settings, clock=clock{L(api, "", ", bus=bus")})

    customers = CustomerService({L(api, "", "bus, ")}Registry("customer", lambda c: c.id), IdGenerator("cus"))
    catalog = CatalogService({L(api, "", "bus, ")}Registry("product", lambda p: p.sku))
    inventory = InventoryService({L(api, "", "bus, ")}settings)
    pricing = PricingService({L(api, "", "bus, ")}settings)
    carts = CartService({L(api, "", "bus, ")}catalog)
    orders = OrderService(
        {L(api, "", "bus,\n        ")}Registry("order", lambda o: o.id), IdGenerator("ord"), clock, carts, pricing, inventory, customers
    )
    payments = PaymentService({L(api, "", "bus, ")}Registry("payment", lambda p: p.id), IdGenerator("pay"), orders)
    shipping = ShippingService({L(api, "", "bus, ")}Registry("shipment", lambda s: s.id), IdGenerator("shp"), orders)
    returns = ReturnsService({L(api, "", "bus, ")}orders, inventory, payments)
    notifications = NotificationService({L(api, "", "bus")})
    app.services = Services(
        customers=customers,
        catalog=catalog,
        inventory=inventory,
        pricing=pricing,
        carts=carts,
        orders=orders,
        payments=payments,
        shipping=shipping,
        returns=returns,
        notifications=notifications,
    )

    for module_name in PLUGIN_MODULES:
        module = importlib.import_module(module_name)
        plugin = module.register(app)
        app.plugins[getattr(plugin, "name", module_name.rsplit(".", 1)[-1])] = plugin
    return app
'''


def cli_init() -> str:
    return '"""Command line front-end."""\n'


def cli_main() -> str:
    return '''"""``python -m cli.main <command>``."""

from __future__ import annotations

import argparse
import sys
from typing import Sequence, TextIO

from app import build_app
from cli.commands import events as events_cmd
from cli.commands import orders as orders_cmd
from cli.commands import report as report_cmd
from cli.commands import stock as stock_cmd
from core.errors import AppError

COMMANDS = {
    "demo": orders_cmd.run_demo,
    "stock": stock_cmd.show_stock,
    "report": report_cmd.show_report,
    "events": events_cmd.list_events,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="shop")
    parser.add_argument("command", choices=sorted(COMMANDS))
    return parser


def main(argv: Sequence[str] | None = None, out: TextIO | None = None) -> int:
    out = out or sys.stdout
    args = build_parser().parse_args(argv)
    app = build_app()
    try:
        COMMANDS[args.command](app, out)
    except AppError as exc:
        out.write(f"error: {exc}\\n")
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
'''


def cli_commands_init() -> str:
    return '"""Sub-commands; each takes ``(app, out)``."""\n'


def cli_commands_orders(api: Api) -> str:
    return f'''"""The scripted demo flow used by ``shop demo``."""

from __future__ import annotations

from typing import TextIO

{api.imports(emits=["customer.upgraded"])}from core.errors import PaymentDeclined


def seed_catalog(app) -> None:
    catalog, inventory = app.services.catalog, app.services.inventory
    catalog.add_product("kb-01", "Keyboard", 4_999)
    catalog.add_product("ms-02", "Mouse", 1_999)
    catalog.add_product("mn-03", "Monitor", 24_999)
    inventory.receive("kb-01", 10)
    inventory.receive("ms-02", 4)
    inventory.receive("mn-03", 2)


def run_demo(app, out: TextIO) -> None:
    seed_catalog(app)
    services = app.services
    alice = services.customers.register("alice@example.test", "Alice")
    bob = services.customers.register("bob@example.test", "Bob")
    services.customers.upgrade(alice.id, "gold")
    # the demo also announces the upgrade on the "marketing" side of the house
    {api.emit("app.bus", "customer.upgraded", '{"customer_id": alice.id, "tier": "gold", "previous": "gold", "source": "demo"}')}

    services.carts.add_item(alice.id, "kb-01", 2)
    services.carts.add_item(alice.id, "ms-02", 1)
    order = services.orders.create_order(alice.id)
    services.payments.capture(order.id, "4242")
    shipment = services.shipping.dispatch(order.id, "ups")
    services.shipping.deliver(shipment.id)

    services.carts.add_item(bob.id, "mn-03", 1)
    declined = services.orders.create_order(bob.id)
    try:
        services.payments.capture(declined.id, "0000")
    except PaymentDeclined as exc:
        out.write(f"{{exc}}\\n")

    out.write(f"{{order.id}} {{services.orders.get(order.id).status}} total={{order.total_cents}}\\n")
    out.write(f"{{declined.id}} {{services.orders.get(declined.id).status}} total={{declined.total_cents}}\\n")
    out.write(f"notifications={{len(services.notifications.outbox)}}\\n")
    out.write(f"audit={{len(app.plugins['audit'].entries)}}\\n")
'''


def cli_commands_stock() -> str:
    return '''"""``shop stock``: on-hand quantities."""

from __future__ import annotations

from typing import TextIO


def show_stock(app, out: TextIO) -> None:
    inventory = app.services.inventory
    if not inventory.stock:
        out.write("(no stock)\\n")
        return
    for sku in sorted(inventory.stock):
        out.write(f"{sku:<8}{inventory.stock[sku]:>6}\\n")
'''


def cli_commands_report() -> str:
    return '''"""``shop report``: plugin summaries."""

from __future__ import annotations

from typing import TextIO


def show_report(app, out: TextIO) -> None:
    metrics = app.plugins["metrics"]
    reporting = app.plugins["reporting"]
    out.write(reporting.summary() + "\\n")
    for name, count in metrics.snapshot().items():
        out.write(f"{name}: {count}\\n")
    out.write(f"revenue_cents={metrics.revenue_cents}\\n")
'''


def cli_commands_events(api: Api) -> str:
    if api.legacy:
        imports = "from core import events\nfrom core.constants import ALL_EVENTS\n"
        body = "    for name in ALL_EVENTS:\n        out.write(f\"{name:<24}{events.handler_count(name):>3}\\n\")\n"
    else:
        imports = "from core.events import EventType\n"
        body = "    for event_type in EventType:\n        out.write(f\"{event_type.value:<24}{len(app.bus.handlers(event_type)):>3}\\n\")\n"
    return f'''"""``shop events``: every event name with its number of subscribers."""

from __future__ import annotations

from typing import TextIO

{imports}

def list_events(app, out: TextIO) -> None:
{body}'''


# ---------------------------------------------------------------------------
# tests/ (visible; identical in both modes and independent of the events API)
# ---------------------------------------------------------------------------


def tests_init() -> str:
    return ""


def tests_helpers() -> str:
    return '''"""Shared fixtures for the visible suite (API-agnostic: only public services are used)."""

from app import build_app


def app_with_catalog():
    app = build_app()
    catalog, inventory = app.services.catalog, app.services.inventory
    catalog.add_product("kb-01", "Keyboard", 4_999)
    catalog.add_product("ms-02", "Mouse", 1_999)
    catalog.add_product("mn-03", "Monitor", 24_999)
    inventory.receive("kb-01", 10)
    inventory.receive("ms-02", 4)
    inventory.receive("mn-03", 2)
    return app


def customer_with_cart(app, email="alice@example.test", items=(("kb-01", 2), ("ms-02", 1))):
    customer = app.services.customers.register(email, email.split("@")[0].title())
    for sku, qty in items:
        app.services.carts.add_item(customer.id, sku, qty)
    return customer
'''


def tests_flow() -> str:
    return '''import unittest

from tests.helpers import app_with_catalog, customer_with_cart


class HappyPathTests(unittest.TestCase):
    def setUp(self):
        self.app = app_with_catalog()
        self.services = self.app.services
        self.alice = customer_with_cart(self.app)

    def test_order_lifecycle(self):
        order = self.services.orders.create_order(self.alice.id)
        self.assertEqual(order.id, "ord-0001")
        self.assertEqual(order.total_cents, 2 * 4_999 + 1_999)
        self.assertEqual(self.services.inventory.available("kb-01"), 8)
        self.assertEqual(self.services.inventory.available("ms-02"), 3)
        payment = self.services.payments.capture(order.id, "4242")
        self.assertEqual(payment.id, "pay-0001")
        self.assertEqual(order.status, "paid")
        shipment = self.services.shipping.dispatch(order.id, "dhl")
        self.assertEqual(order.status, "shipped")
        self.services.shipping.deliver(shipment.id)
        self.assertEqual(shipment.status, "delivered")
        self.assertEqual(order.history, ["created", "paid", "shipped"])

    def test_plugins_react_to_the_flow(self):
        order = self.services.orders.create_order(self.alice.id)
        self.services.payments.capture(order.id, "4242")
        shipment = self.services.shipping.dispatch(order.id, "ups")
        self.services.shipping.deliver(shipment.id)
        plugins = self.app.plugins
        self.assertEqual(plugins["metrics"].snapshot(), {
            "order.created": 1, "order.paid": 1, "shipment.delivered": 1,
        })
        self.assertEqual(plugins["loyalty"].points[self.alice.id], 119 * self.app.settings.loyalty_points_per_dollar)
        self.assertEqual(self.services.notifications.sent_via("email"), [
            "Order ord-0001 received", "Order ord-0001 shipped via ups",
        ])
        self.assertEqual(self.services.notifications.sent_via("sms"), ["Delivered: ord-0001"])
        self.assertEqual([name for _, name, _ in plugins["webhooks"].deliveries], ["order.paid", "shipment.dispatched"])
        self.assertEqual(plugins["warehouse_sync"].shipped, ["ord-0001"])
        self.assertEqual(plugins["warehouse_sync"].pending, {})
        self.assertEqual(plugins["reporting"].summary(), "delivered=1 cancelled=0 captured_cents=11997")
        self.assertIn("audit", plugins)
        self.assertGreaterEqual(plugins["audit"].count("notification.sent"), 3)

    def test_audit_sees_every_event_in_order(self):
        order = self.services.orders.create_order(self.alice.id)
        names = self.app.plugins["audit"].names()
        self.assertEqual(names[0], "customer.registered")
        self.assertEqual(names.count("cart.item_added"), 2)
        self.assertLess(names.index("inventory.reserved"), names.index("order.created"))
        self.assertEqual(self.app.plugins["audit"].entries[-1][0], "notification.sent")
        self.assertEqual(order.status, "created")


if __name__ == "__main__":
    unittest.main()
'''


def tests_inventory_and_fraud() -> str:
    return '''import unittest

from app import build_app
from core.config import Settings
from core.errors import InsufficientStock, InvalidTransition, ValidationError
from tests.helpers import app_with_catalog, customer_with_cart


class InventoryTests(unittest.TestCase):
    def test_low_stock_alerts(self):
        app = app_with_catalog()
        customer = customer_with_cart(app, items=(("ms-02", 2),))
        app.services.orders.create_order(customer.id)
        remaining = app.services.inventory.available("ms-02")
        self.assertEqual(remaining, 2)
        self.assertEqual(app.plugins["stock_guard"].alerts, [("ms-02", 2)])
        self.assertEqual(app.plugins["slack_alerts"].alerts, ["low stock ms-02=2"])
        self.assertEqual(app.services.notifications.sent_via("ops"), ["Low stock: ms-02 (2 left)"])

    def test_insufficient_stock_leaves_everything_untouched(self):
        app = app_with_catalog()
        customer = customer_with_cart(app, items=(("mn-03", 3),))
        with self.assertRaises(InsufficientStock):
            app.services.orders.create_order(customer.id)
        self.assertEqual(app.services.inventory.available("mn-03"), 2)
        self.assertEqual(len(app.services.orders.orders), 0)
        self.assertNotIn("order.created", app.plugins["audit"].names())

    def test_cancel_releases_stock(self):
        app = app_with_catalog()
        customer = customer_with_cart(app)
        order = app.services.orders.create_order(customer.id)
        app.services.orders.cancel(order.id, "customer request")
        self.assertEqual(app.services.inventory.available("kb-01"), 10)
        self.assertEqual(app.plugins["warehouse_sync"].pending, {})
        self.assertEqual(app.plugins["reporting"].cancelled, [(order.id, "customer request")])
        with self.assertRaises(InvalidTransition):
            app.services.orders.mark_paid(order.id)


class FraudTests(unittest.TestCase):
    def test_large_orders_are_cancelled_for_review(self):
        app = app_with_catalog()
        customer = customer_with_cart(app, items=(("mn-03", 2), ("kb-01", 10)))
        order = app.services.orders.create_order(customer.id)
        self.assertGreater(order.total_cents, app.settings.fraud_limit_cents)
        self.assertEqual(order.status, "cancelled")
        self.assertEqual(app.plugins["fraud_check"].flagged, [order.id])
        self.assertEqual(app.plugins["slack_alerts"].alerts[-1], f"fraud hold on {order.id}")
        self.assertEqual(app.services.inventory.available("mn-03"), 2)
        with self.assertRaises(ValidationError):
            app.services.payments.capture(order.id, "4242")

    def test_custom_settings(self):
        app = build_app(settings=Settings(fraud_limit_cents=1))
        app.services.catalog.add_product("kb-01", "Keyboard", 4_999)
        app.services.inventory.receive("kb-01", 5)
        customer = customer_with_cart(app, items=(("kb-01", 1),))
        order = app.services.orders.create_order(customer.id)
        self.assertEqual(order.status, "cancelled")


if __name__ == "__main__":
    unittest.main()
'''


def tests_payments_and_returns() -> str:
    return '''import unittest

from core.errors import PaymentDeclined, ValidationError
from tests.helpers import app_with_catalog, customer_with_cart


class PaymentTests(unittest.TestCase):
    def test_declined_card(self):
        app = app_with_catalog()
        customer = customer_with_cart(app)
        order = app.services.orders.create_order(customer.id)
        with self.assertRaises(PaymentDeclined):
            app.services.payments.capture(order.id, "0000")
        self.assertEqual(order.status, "created")
        self.assertEqual(app.plugins["metrics"].snapshot(), {"order.created": 1, "payment.failed": 1})
        self.assertEqual(app.services.notifications.sent_via("sms"), [
            "Payment for ord-0001 failed: card declined",
        ])
        self.assertEqual(app.plugins["slack_alerts"].alerts[-1], "payment failed for ord-0001: card declined")
        payment = app.services.payments.capture(order.id, "4242")
        self.assertEqual(payment.amount_cents, order.total_cents)

    def test_return_refunds_and_restocks(self):
        app = app_with_catalog()
        customer = customer_with_cart(app)
        order = app.services.orders.create_order(customer.id)
        app.services.payments.capture(order.id, "4242")
        shipment = app.services.shipping.dispatch(order.id, "fedex")
        app.services.shipping.deliver(shipment.id)
        points_before = app.plugins["loyalty"].points[customer.id]
        refunded = app.services.returns.process_return(order.id)
        self.assertEqual(refunded, ["pay-0001"])
        self.assertEqual(order.status, "returned")
        self.assertEqual(app.services.inventory.available("kb-01"), 10)
        self.assertEqual(app.plugins["loyalty"].points[customer.id], 0)
        self.assertGreater(points_before, 0)
        self.assertEqual(app.services.notifications.sent_via("email")[-1], "Refund of 11997 cents for ord-0001")
        with self.assertRaises(ValidationError):
            app.services.returns.process_return(order.id)


class CustomerTests(unittest.TestCase):
    def test_registration_and_upgrade(self):
        app = app_with_catalog()
        alice = app.services.customers.register("alice@example.test", "Alice Liddell")
        with self.assertRaises(ValidationError):
            app.services.customers.register("alice@example.test", "Again")
        app.services.customers.upgrade(alice.id, "gold")
        self.assertEqual(app.plugins["search_indexer"].index[alice.id], {
            "name": "Alice Liddell", "email": "alice@example.test", "tier": "gold",
        })
        self.assertEqual(app.plugins["search_indexer"].search("liddell"), [alice.id])
        self.assertEqual(app.plugins["loyalty"].points[alice.id], 100)
        self.assertEqual(app.plugins["cache_invalidator"].invalidated, [f"customer:{alice.id}"])
        self.assertEqual(app.plugins["analytics"].signups, 1)


if __name__ == "__main__":
    unittest.main()
'''


def tests_cli() -> str:
    return '''import io
import unittest

from cli.main import main


class CliTests(unittest.TestCase):
    def test_demo(self):
        out = io.StringIO()
        self.assertEqual(main(["demo"], out=out), 0)
        self.assertEqual(out.getvalue().splitlines(), [
            "payment for ord-0002 declined: card declined",
            "ord-0001 shipped total=10798",
            "ord-0002 created total=24999",
            "notifications=7",
            "audit=27",
        ])

    def test_events_lists_every_event_with_subscriber_counts(self):
        out = io.StringIO()
        self.assertEqual(main(["events"], out=out), 0)
        lines = out.getvalue().splitlines()
        self.assertEqual(len(lines), 16)
        names = [line.split()[0] for line in lines]
        self.assertEqual(names[:4], ["customer.registered", "customer.upgraded", "cart.item_added", "order.created"])
        counts = {line.split()[0]: int(line.split()[1]) for line in lines}
        self.assertEqual(counts["order.created"], 6)
        self.assertEqual(counts["notification.sent"], 2)
        self.assertTrue(all(count >= 1 for count in counts.values()))

    def test_stock_and_report(self):
        out = io.StringIO()
        self.assertEqual(main(["stock"], out=out), 0)
        self.assertEqual(out.getvalue(), "(no stock)\\n")
        out = io.StringIO()
        self.assertEqual(main(["report"], out=out), 0)
        self.assertEqual(out.getvalue(), "delivered=0 cancelled=0 captured_cents=0\\nrevenue_cents=0\\n")


if __name__ == "__main__":
    unittest.main()
'''


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

STYLES = ["module", "names", "alias", "const"]


def generate(legacy: bool, seed: int) -> dict[str, str]:
    rng = random.Random(seed)
    files: dict[str, str] = {}

    # Pick an import style per module deterministically.
    styled_modules = [
        "services.customers", "services.catalog", "services.inventory", "services.pricing",
        "services.carts", "services.orders", "services.payments", "services.shipping",
        "services.returns", "services.notifications", "cli.commands.orders",
        *[f"plugins.{name}" for name in PLUGINS],
    ]
    styles = {name: rng.choice(STYLES) for name in styled_modules}
    plugin_order = list(PLUGINS)
    rng.shuffle(plugin_order)
    # audit must come first so its log is complete and in a predictable order
    plugin_order.remove("audit")
    plugin_order.insert(0, "audit")
    settings_rng = random.Random(seed + 1)

    def api(name: str) -> Api:
        return Api(legacy, styles[name])

    files["core/__init__.py"] = core_init()
    files["core/events.py"] = core_events(legacy)
    files["core/constants.py"] = core_constants(legacy)
    files["core/errors.py"] = core_errors()
    files["core/models.py"] = core_models()
    files["core/clock.py"] = core_clock()
    files["core/ids.py"] = core_ids()
    files["core/registry.py"] = core_registry()
    files["core/config.py"] = core_config(settings_rng)

    files["services/__init__.py"] = services_init()
    files["services/customers.py"] = service_customers(api("services.customers"))
    files["services/catalog.py"] = service_catalog(api("services.catalog"))
    files["services/inventory.py"] = service_inventory(api("services.inventory"))
    files["services/pricing.py"] = service_pricing(api("services.pricing"))
    files["services/carts.py"] = service_carts(api("services.carts"))
    files["services/orders.py"] = service_orders(api("services.orders"))
    files["services/payments.py"] = service_payments(api("services.payments"))
    files["services/shipping.py"] = service_shipping(api("services.shipping"))
    files["services/returns.py"] = service_returns(api("services.returns"))
    files["services/notifications.py"] = service_notifications(api("services.notifications"))

    files["plugins/__init__.py"] = plugins_init(plugin_order)
    for name in PLUGINS:
        files[f"plugins/{name}.py"] = PLUGIN_GENERATORS[name](api(f"plugins.{name}"))

    files["app.py"] = app_module(Api(legacy, "module"))
    files["cli/__init__.py"] = cli_init()
    files["cli/main.py"] = cli_main()
    files["cli/commands/__init__.py"] = cli_commands_init()
    files["cli/commands/orders.py"] = cli_commands_orders(api("cli.commands.orders"))
    files["cli/commands/stock.py"] = cli_commands_stock()
    files["cli/commands/report.py"] = cli_commands_report()
    files["cli/commands/events.py"] = cli_commands_events(Api(legacy, "module"))

    files["tests/__init__.py"] = tests_init()
    files["tests/helpers.py"] = tests_helpers()
    files["tests/test_flow.py"] = tests_flow()
    files["tests/test_inventory_and_fraud.py"] = tests_inventory_and_fraud()
    files["tests/test_payments_and_returns.py"] = tests_payments_and_returns()
    files["tests/test_cli.py"] = tests_cli()
    files["README.md"] = readme()
    return files


def readme() -> str:
    return """# shop

A small event-driven order management back-end used for exercises.

```
python -m cli.main demo
python -m unittest discover -s tests -t .
```

Packages: `core/` (models, registries, settings, the event system), `services/`
(business logic), `plugins/` (event subscribers), `cli/` (commands). `app.py`
wires everything together with `build_app()`.
"""


def write_tree(files: dict[str, str], root: Path, *, clean: bool) -> int:
    if clean and root.exists():
        shutil.rmtree(root)
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return len(files)


def reference_overlay(seed: int) -> dict[str, str]:
    legacy = generate(True, seed)
    new = generate(False, seed)
    return {rel: content for rel, content in new.items() if legacy.get(rel) != content}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", type=Path, help="output directory (defaults depend on --reference)")
    parser.add_argument("--reference", action="store_true", help="emit the migrated files (reference solution overlay)")
    parser.add_argument("--clean", action="store_true", help="delete the output directory first")
    parser.add_argument("--check", action="store_true", help="only report call-site statistics")
    args = parser.parse_args(argv)

    if args.check:
        legacy = generate(True, args.seed)
        overlay = reference_overlay(args.seed)
        import re

        emit_sites = sum(len(re.findall(r"\bemit\(", c)) for r, c in legacy.items() if r != "core/events.py")
        on_sites = sum(len(re.findall(r"\bon\(", c)) for r, c in legacy.items() if r != "core/events.py")
        print(f"modules: {sum(1 for r in legacy if r.endswith('.py'))}")
        print(f"legacy emit call sites: {emit_sites}, on call sites: {on_sites}")
        print(f"reference overlay files: {len(overlay)}")
        return 0

    if args.reference:
        out = args.out or DEFAULT_REFERENCE
        count = write_tree(reference_overlay(args.seed), out, clean=args.clean)
    else:
        out = args.out or DEFAULT_WORKSPACE
        count = write_tree(generate(True, args.seed), out, clean=args.clean)
    print(f"wrote {count} files to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
