# Dashboard style references

The four images in this folder are the owner's mood board for the dashboard.
Every visual decision in `dashboard/web/src/app.css` should trace back to them.

| file | what to take from it |
|---|---|
| `1.webp` | point-mesh wireframe globe: white points and hairlines on pure black, monochrome, delicate, no glow |
| `2.webp` | pixel-grid data map with 1px-outlined cells, purple→orange heat palette used only for data, rulers with zero-padded tick labels, a `seed / dir / grid / cores` metadata line, a `dist` legend bar; engraved grayscale relief |
| `3.webp` | terminal + engineering-drawing UI: monospace everywhere, cream text on black, bordered panels with in-border titles ("section A-A"), label/value stat rows, contour-line drawing, dimension callouts, one warm orange-red accent on key numbers, red corner crop-marks on the active element, bottom status bar with uppercase labels and a bar sparkline, project spine in the left rail |
| `4.webp` | circular HUD gauge: concentric thin rings with tick marks and small labels on a dark ground |

Ground `#050505`; text cream `#e8e4d8`; muted `#8a8780`; hairlines cream at ~22% alpha;
accent `#e8623c`; heat palette only inside data maps. No teal, no glow, no filled cards,
no animated backgrounds.
