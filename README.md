# forgejo-release-mirror

Copy published Forgejo releases and their attached files to an existing GitHub
repository. Release notes and prerelease flags follow Forgejo. New GitHub
releases stay in draft until every attachment has passed verification.

This tool manages releases. Configure Git mirroring separately so the GitHub
tags exist before running it.

## Behavior

- Require each destination tag to resolve to the same commit as its source tag.
- Download each source asset, check its size, and calculate its SHA-256 digest.
- Verify uploaded assets against GitHub's digest, or download them again when
  GitHub does not provide a digest.
- Resume an interrupted upload on the next run. Matching assets are retained.
- Refuse to replace a differing asset in an already published GitHub release.
- Preserve extra destination assets, releases, and tags. Nothing is deleted
  except a mismatching asset belonging to a draft being reconciled.
- Ignore source drafts, unpublished releases, and non-version tags.

The minimum version compares the numeric major, minor, and patch components.
For example, `1.2.0-rc.1` is included by a minimum of `1.2.0`; the source's
prerelease flag is copied independently. Run one mirror process per destination
repository at a time.

## Installation

Python 3.11 or newer is required. The application has no runtime dependencies
outside the Python standard library.

From a checkout:

```sh
uv tool install .
forgejo-release-mirror --help
```

The Nix flake also provides `packages.<system>.default` and `apps.<system>.default`.
Run `nix build` from the checkout to build the executable.

## Usage

Provide `FORGEJO_READ_TOKEN` and `GITHUB_TOKEN` through the environment. The
source token needs read access to the repository and its release attachments.
The destination token needs permission to write releases in the selected
GitHub repository (Contents: write for a fine-grained token). Both repositories
must already exist.

The following command uses your configured origin and repository names:

```sh
forgejo-release-mirror \
  --forgejo-origin "$FORGEJO_ORIGIN" \
  --source-repository "$SOURCE_REPOSITORY" \
  --destination-repository "$DESTINATION_REPOSITORY" \
  --minimum-version 0.1.0 \
  --dry-run
```

Omit `--destination-repository` when the owner and repository name are the same
on both services. The Forgejo origin contains only the scheme and host, with
an optional port. Forgejo installations under a URL subpath and GitHub
Enterprise are not supported in this release.

`--dry-run` checks tag identity and lists eligible release assets. It performs
no writes or asset downloads, so it does not verify asset bytes or upload
permissions. Remove `--dry-run` to reconcile releases.

Success produces one JSON object on stdout. Normal runs report each tag's
`created`, `updated`, and `uploaded_assets` values. Preview runs report an
`action` (`create` or `reconcile`) and asset names. A preview's `reconcile`
does not imply an actual write will be needed. Failures produce a JSON error
on stderr and exit with status 1; argument errors exit with status 2.

Repeated successful runs perform no release writes when metadata and assets
already match. They still download source assets to verify their contents.
A failed run can have completed earlier releases or left a draft for retry.

## NixOS service

Import `nixosModules.default` from this flake and configure
`services.forgejo-release-mirror`. Required settings are `forgejoOrigin`,
`sourceRepository`, `minimumVersion`, and `environmentFile`. The environment
file contains the two token variables and must be provisioned outside the Nix
store, for example using sops-nix. `destinationRepository` defaults to the source
repository name. `onCalendar` defaults to every five minutes.

The `forgejo-release-mirror.service` runs as a dynamic user with a private
temporary directory. Its timer serializes runs on that machine. Inspect the
service journal for the JSON result; a successful service run proves only the
configured mirror operation, not any downstream deployment.

## Development

```sh
uv sync --locked
uv run python -m unittest discover -s tests -v
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv build
```

Tests use fixtures and loopback HTTP servers. They require no service tokens
and do not create releases on external services. Changes should preserve the
tag checks, published-asset protection, and draft-before-publish behavior.

## License
Licensed under MIT.
