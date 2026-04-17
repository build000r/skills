# Adapter Matrix

Pick the repo's existing mutation tool if one is already wired into config or
CI. Otherwise use the default adapter for the language below.

## Selection Order

1. Existing repo-native mutation tool and config
2. Ecosystem default adapter in this file
3. A newly installed adapter only when the user wants setup work

## Rust

- Default adapter: `cargo-mutants`
- Detect with: `Cargo.toml`, `.cargo/mutants.toml`, `mutants.out/`
- Install: `cargo install --locked cargo-mutants`
- Full run: `cargo mutants`
- Narrow scope: `cargo mutants --file src/foo.rs`
- Preview scope: `cargo mutants --list -f src/foo.rs`
- Notes:
  - By default it works on a copy of the tree and writes output under
    `mutants.out/`.
  - Avoid `--in-place` unless you are in a disposable checkout.

## Python

- Default adapter: `mutmut`
- Detect with: `pyproject.toml`, `setup.cfg`, `mutants/`
- Install: `pip install mutmut`
- Full run: `mutmut run`
- Narrow scope:
  - prefer config such as `[tool.mutmut] paths_to_mutate = ["src/"]`
  - use wildcard reruns like `mutmut run "pkg.module*"` when supported by the
    target naming
- Browse survivors: `mutmut browse`
- Notes:
  - `mutmut` keeps incremental state in `mutants/`.
  - If you need a true fresh run, remove that directory first.

## JavaScript / TypeScript

- Default adapter: `StrykerJS`
- Detect with: `package.json`, `stryker.conf.json`, `stryker.conf.js`,
  `stryker.config.mjs`
- Install:
  - `npm i -D @stryker-mutator/core`
  - add the repo's matching test-runner plugin, for example
    `@stryker-mutator/jest-runner`
- Full run: `npx stryker run`
- Narrow scope:
  - prefer committed `mutate` patterns in Stryker config, for example
    `["src/**/*.ts", "!src/generated/**"]`
  - narrow further before running instead of mutating the whole repo
- Notes:
  - Prefer the repo's existing Stryker config over ad hoc CLI overrides.
  - Keep TypeScript checker and test-runner plugins aligned with the repo's
    stack when they are already in use.

## Swift

- Default adapter: `muter`
- Detect with: `muter.conf.yml`, `muterReport.json`, `muter-report.json`,
  `Package.swift`, any `*.xcodeproj` / `*.xcworkspace`
- Install: `brew install muter-mutation-testing/formulae/muter`
- Full run: `muter run`
- Narrow scope: `muter run --files-to-mutate "Sources/Auth/**/*.swift"`
- Machine-readable output: `muter run --format json --output muterReport.json`
  (or `muter run --output-json`)
- Preview scope: `muter run --skip-coverage --format xcode` for a dry-pass
- Notes:
  - `muter.conf.yml` at the project root declares the test command (usually
    `xcodebuild` with scheme + destination, or `swift test` for SPM packages).
  - Running on an iOS app requires a simulator destination; the CI recipe is
    typically the same destination used for `xcodebuild test`.
  - Muter rebuilds and re-runs the test suite once per mutant, so mutation
    passes are expensive — keep `--files-to-mutate` as narrow as possible.
  - The `/crap` skill's `crap-swift-cobertura` recipe produces the coverage
    artifact `muter` honors when skipping uncovered mutants.

## Unsupported Or Risky Cases

Stop and explain the gap when any of these is true:

- there is no maintained adapter for the language in this repo
- the baseline test path is red or too flaky to trust
- the only available run would mutate the entire repo and the user did not ask
  for that cost
- the adapter requires destructive in-place mutation and there is no disposable
  checkout or clean recovery path
