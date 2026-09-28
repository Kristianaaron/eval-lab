# Söhne Mono

The dashboard is set in Söhne Mono (Klim Type Foundry). The font is licensed
and is not committed here. To serve it with the dashboard, copy your licensed
web files into this folder with these names:

    soehne-mono-buch.woff2          (regular, weight 400)
    soehne-mono-kraftig.woff2       (medium, weight 500)
    soehne-mono-buch-kursiv.woff2   (italic, weight 400)

Vite copies `public/` into `dist/`, so `npm run build` picks them up. If the
files are absent the page uses a locally installed Söhne Mono, and otherwise
JetBrains Mono.
