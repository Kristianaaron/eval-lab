# Migrate the event system to a typed, instance-based `EventBus`

This repository is a small event-driven order management back-end (Python 3.11+,
standard library only): `core/` (models, registries, settings, the event system),
`services/` (business logic), `plugins/` (event subscribers) and `cli/`, wired
together by `app.py::build_app()`. The visible suite is green:

```
python -m unittest discover -s tests -t .
```

Today every module talks to a **process-global, string-keyed** event registry in
`core/events.py` (`emit(name, payload)`, `on(name, handler)`, `off`,
`handler_count`, `reset`, `_HANDLERS`), with event names spelled as string
literals or as the `EVENT_*` constants / `ALL_EVENTS` tuple in
`core/constants.py`. Modules import it in several different ways. Because the
registry is global, two applications cannot coexist in one process and
`build_app()` has to wipe it on every call.

Migrate the **whole** code base to the API below, delete the legacy API, and keep
every visible test passing without modifying anything under `tests/`. A hidden
suite will additionally check the new API's contract, that the legacy API is
gone from every module, and that end-to-end behaviour is unchanged.

## The new `core/events.py`

```python
class EventType(Enum):
    CUSTOMER_REGISTERED = "customer.registered"
    CUSTOMER_UPGRADED = "customer.upgraded"
    CART_ITEM_ADDED = "cart.item_added"
    ORDER_CREATED = "order.created"
    ORDER_PAID = "order.paid"
    ORDER_CANCELLED = "order.cancelled"
    ORDER_SHIPPED = "order.shipped"
    INVENTORY_RESERVED = "inventory.reserved"
    INVENTORY_RELEASED = "inventory.released"
    INVENTORY_LOW = "inventory.low"
    PAYMENT_CAPTURED = "payment.captured"
    PAYMENT_FAILED = "payment.failed"
    PAYMENT_REFUNDED = "payment.refunded"
    SHIPMENT_DISPATCHED = "shipment.dispatched"
    SHIPMENT_DELIVERED = "shipment.delivered"
    NOTIFICATION_SENT = "notification.sent"

@dataclass(frozen=True)
class Event:
    type: EventType
    payload: Mapping[str, Any] = field(default_factory=dict)
    # constructing an Event whose type is not an EventType raises TypeError

Handler = Callable[[Event], None]

class EventBus:
    def subscribe(self, event_type: EventType, handler: Handler) -> None
    def unsubscribe(self, event_type: EventType, handler: Handler) -> None
    def publish(self, event: Event) -> int
    def handlers(self, event_type: EventType) -> tuple[Handler, ...]
    def clear(self) -> None

def default_bus() -> EventBus
def reset_default_bus() -> None
```

Contract:

- `EventType` has exactly these sixteen members, in this order, with these values
  (they are the old string names). Handlers receive the whole `Event` and read
  `event.payload`; payload keys and values are unchanged from today.
- `subscribe`, `unsubscribe` and `handlers` raise `TypeError` when `event_type`
  is not an `EventType` (a plain string must be rejected). `publish` raises
  `TypeError` when given anything but an `Event`.
- Subscribing the same handler to the same type twice keeps a single
  subscription; unsubscribing a handler that is not subscribed is a no-op.
- `publish` calls the handlers of the event's type in subscription order and
  returns how many it called (`0` when there are none). It iterates over a
  snapshot: handlers subscribed or unsubscribed while an event is being
  published do not affect that publish.
- Every `EventBus()` is independent; `clear()` drops all of its subscriptions.
- `default_bus()` lazily creates one process-wide bus and returns the same
  instance until `reset_default_bus()` discards it. Nothing in this repository
  may rely on it: all wiring goes through `build_app`.

## Wiring

- `build_app(bus: EventBus | None = None, settings: Settings | None = None) -> App`.
  A caller-supplied bus is used as-is; otherwise `build_app` creates a **new**
  `EventBus()` for that app (never `default_bus()`). `App` gets a `bus`
  attribute, and `build_app` no longer resets anything global.
- Every service class in `services/` takes the bus as its **first** constructor
  argument and keeps it as `self.bus` (also the ones that do not publish today,
  so the container stays uniform); they publish with `self.bus.publish(Event(...))`.
- Plugins keep their `register(app)` entry point and subscribe through
  `app.bus.subscribe(EventType.X, handler)`; the audit plugin must subscribe to
  every member of `EventType`. Code that publishes from a plugin or a CLI command
  uses `app.bus`.
- `cli/commands/events.py` lists every `EventType` member's value with the
  number of handlers on `app.bus`, in enum order, keeping the current line format.

## Clean-up

- Remove `emit`, `on`, `off`, `handler_count`, `reset` and `_HANDLERS` from
  `core/events.py`, and every `EVENT_*` constant plus `ALL_EVENTS` from
  `core/constants.py` (the other constants there stay). No module may import or
  call the legacy names afterwards; `from core.events import ...` may only bring
  in `Event`, `EventType`, `EventBus`, `Handler`, `default_bus`, `reset_default_bus`.
- Every module under `core/`, `services/`, `plugins/` and `cli/` (plus `app.py`)
  must still import cleanly, and `plugins/__init__.py::PLUGIN_MODULES` keeps its
  fifteen entries.

Legacy usages are spread across roughly thirty modules with varied import
styles (`from core import events`, `from core.events import emit, on`,
`import core.events as ev`, constants from `core.constants`), so inspect the tree
systematically rather than fixing only what the tests point at. Run the visible
suite when you are done.
