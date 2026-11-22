# wsh-pve docs

Documentation site for [wsh-pve](https://github.com/hwinther/wsh-pve), built with [Astro](https://astro.build) and [Starlight](https://starlight.astro.build). Published to [debian.wshosting.no](https://debian.wshosting.no/) by [`repo-update.yml`](../.github/workflows/repo-update.yml).

## Project Structure

Inside of this project, you'll see the following folders and files:

```
.
├── public/
├── src/
│   ├── assets/
│   ├── content/
│   │   ├── docs/
│   └── content.config.ts
├── astro.config.mjs
├── package.json
└── tsconfig.json
```

Starlight looks for `.md` or `.mdx` files in the `src/content/docs/` directory. Each file is exposed as a route based on its file name.

Images can be added to `src/assets/` and embedded in Markdown with a relative link.

Static assets, like favicons, can be placed in the `public/` directory.

## Commands

All commands are run from this directory (`docs/`), from a terminal:

| Command                   | Action                                           |
| :------------------------ | :----------------------------------------------- |
| `npm install`             | Installs dependencies                            |
| `npm run dev`             | Starts local dev server at `localhost:4321`      |
| `npm run build`           | Build the production site to `./dist/`           |
| `npm run preview`         | Preview the build locally, before deploying      |
| `npm run astro ...`       | Run CLI commands like `astro add`, `astro check` |
| `npm run astro -- --help` | Get help using the Astro CLI                     |

## This site's own parts

- `npm run generate-packages` (also run before `dev` and `build`) writes `src/data/packages.json`
  from the apt repository's `Packages` file, or from the changelog patches in `submodules/` as a
  fallback (`scripts/generate-docs-packages.js`).
- `npm run fetch-media` downloads the `media` GitHub release (the sparc lab recordings) into
  `public/recordings/`, so a local site serves them at `/recordings/` as the deployed one does
  (`scripts/fetch-docs-media.js`). Recordings are never committed.
- Pages are in `src/content/docs/guides/` and `src/content/docs/reference/`; the sidebar is listed in
  `astro.config.mjs`. Components in `src/components/`: `LabCast` and `LabVideo` (the recording
  players), `PackageVersions` and `LivingMuseum`.

## Learn more

Check out [Starlight's docs](https://starlight.astro.build/), read [the Astro documentation](https://docs.astro.build), or jump into the [Astro Discord server](https://astro.build/chat).
