# shop

A small event-driven order management back-end used for exercises.

```
python -m cli.main demo
python -m unittest discover -s tests -t .
```

Packages: `core/` (models, registries, settings, the event system), `services/`
(business logic), `plugins/` (event subscribers), `cli/` (commands). `app.py`
wires everything together with `build_app()`.
