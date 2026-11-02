# LiteInjector website

Documentation and tutorials of LiteInjector, built with [Astro Starlight](https://starlight.astro.build).

```console
$ npm install
$ npm run dev          # local preview with live reload
$ npm run api          # generate the Python API reference in public/api (needs `pip install pdoc`)
$ npm run build:all    # API reference + static site in dist/
$ npm run preview      # serve dist/
```

Pages are in `src/content/docs` (Markdown/MDX), figures in `src/assets/figures`, the sidebar in `astro.config.mjs`.

To build for a sub-path deployment such as GitHub Pages, set `SITE_URL` and `SITE_BASE`, e.g.
`SITE_URL=https://<owner>.github.io SITE_BASE=/LiteInjector npm run build:all`.
