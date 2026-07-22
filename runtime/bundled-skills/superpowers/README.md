# Superpowers Bundled Skill

This bundle wraps a pinned, license-compatible subset of the
`obra/superpowers` workflow skill chain (MIT) for use by Lang Drill Agent's
creative runtime. It is loaded only when the workflow resolver classifies a
request as a complex, multi-file coding task; ordinary chat, learning drills,
screenshot imports and memory workflows never inject this bundle.

## Provenance

- Upstream repository: https://github.com/obra/superpowers
- Pinned origin commit: `d884ae04edebef577e82ff7c4e143debd0bbec99`
- License: MIT (see `LICENSE`).

## Skill chain

The bundle exposes the following ordered skill references that the creative
runtime can attach to a plan when the request intent is `multi_file_feature`:

1. `using-superpowers`
2. `brainstorming`
3. `writing-plans`
4. `using-git-worktrees`
5. `test-driven-development`
6. `requesting-code-review`
7. `verification-before-completion`

## Verification

Every file shipped in this bundle is recorded in `manifest.json` together with
its SHA-256 hash. The desktop runtime preparation step (Plan 06) recomputes
these hashes and fails the build on mismatch or missing artifacts before the
bundle can be enabled for a creative run.
