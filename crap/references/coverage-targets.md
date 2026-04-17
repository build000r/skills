# Coverage Target Examples

Use these examples when `/crap` needs machine-readable coverage artifacts and
the repo does not already export them.

If the scope does not have a usable baseline test path yet, start with
[testing-bootstrap.md](testing-bootstrap.md) first. Coverage flags do not
replace a missing harness.

## Selection Rules

- Prefer additive targets such as `pytest-cov-xml` over mutating canonical
  fast-path targets like `test` or `pytest`.
- If a repo already uses `make`, put the coverage export behind a Make target.
- If the repo has no tests yet, bootstrap the smallest baseline first, then add
  the coverage target as a sibling entrypoint.
- Keep artifact names explicit:
  - Python -> `coverage.xml`
  - TypeScript -> `lcov.info`
  - Rust -> `lcov.info`
  - Swift -> `coverage.xml` (Cobertura, produced from `.xcresult` via `xcresultparser`)
- In mixed-language repos, keep per-language coverage targets separate, then
  add an optional aggregate `make crap` target that runs coverage first and the
  analyzer second.
- If the user started from repo root, prefer the aggregate target over
  reporting one package as if it were the whole repo.

## Python / pytest-cov

Use when the repo already runs tests via `pytest` and has `pytest-cov`
available.

```make
.PHONY: pytest-cov-xml
pytest-cov-xml: ensure-venv ## Run tests with XML coverage for /crap
	cd {pkg_dir} && $(ACTIVATE) && \
	pytest {test_path} \
	  --cov={coverage_source} \
	  --cov-report=term-missing:skip-covered \
	  --cov-report=xml:coverage.xml \
	  -n $(PYTEST_WORKERS)
```

Typical placeholders:

- `{pkg_dir}` -> `packages/python-server-quickstart`
- `{test_path}` -> `tests` or `tests/domains/`
- `{coverage_source}` -> import package such as `spaps_server_quickstart`

## TypeScript / Vitest

Use when the repo already uses `vitest`. This requires a Vitest coverage
provider such as `@vitest/coverage-v8` or `@vitest/coverage-istanbul`.

```make
.PHONY: vitest-cov-lcov
vitest-cov-lcov: ## Run Vitest with lcov output for /crap
	cd {package_dir} && \
	npx vitest run \
	  --coverage.enabled true \
	  --coverage.reporter=lcov \
	  --coverage.reporter=text
```

If the repo uses `package.json` scripts already, the target can delegate:

```make
.PHONY: vitest-cov-lcov
vitest-cov-lcov:
	cd {package_dir} && npm run test -- --coverage --coverage.reporter=lcov --coverage.reporter=text
```

Expected artifact: `{package_dir}/coverage/lcov.info`

## Rust / cargo-llvm-cov

Use when the repo is Rust-first and wants an `lcov.info` artifact.

```make
.PHONY: cargo-cov-lcov
cargo-cov-lcov: ## Run Rust coverage with lcov output for /crap
	cd {crate_dir} && cargo llvm-cov --lcov --output-path lcov.info
```

If `cargo llvm-cov` is not installed, note the prerequisite before adding the
target:

```bash
cargo install cargo-llvm-cov
```

## Swift / Xcode (xcresultparser)

Use when the scope is an iOS/macOS/tvOS/watchOS project that runs tests via
`xcodebuild`. The binary `.xcresult` bundle is converted to Cobertura XML by
[xcresultparser](https://github.com/a7ex/xcresultparser), which `/crap` already
reads.

Prerequisites:

```bash
brew install xcresultparser
pip install lizard    # required by analyze_crap.py for Swift function parsing
```

```make
.PHONY: crap-swift-cobertura
crap-swift-cobertura: ## Run Swift tests and emit Cobertura coverage for /crap
	xcodebuild \
	  -scheme {scheme} \
	  -destination '{destination}' \
	  -resultBundlePath build/test.xcresult \
	  -enableCodeCoverage YES \
	  test
	xcresultparser -o cobertura build/test.xcresult > coverage.xml
```

Typical placeholders:

- `{scheme}` -> Xcode scheme (e.g., `MyApp`)
- `{destination}` -> simulator destination, e.g.
  `platform=iOS Simulator,name=iPhone 16`

Expected artifact: `coverage.xml` at the repo root (Cobertura format).

If `xcresultparser` cannot be installed, the zero-install fallback is
`xcrun xccov view --report --json build/test.xcresult`, but CRAP does not read
raw xccov JSON; you would need a converter such as `xccov2lcov`. Prefer
`xcresultparser` when available.

## Optional Aggregate Target

Use when the repo wants a single entrypoint that refreshes artifacts and runs
the analyzer.

```make
.PHONY: crap
crap: pytest-cov-xml vitest-cov-lcov cargo-cov-lcov crap-swift-cobertura ## Refresh coverage artifacts and run /crap
	python3 {crap_script} {repo_root}
```

Only include the dependencies that actually exist in the repo.

If only one dependency exists today, the resulting rerun is package-scoped or
path-scoped, not repo-wide.

## Editing Guidance

- Prefer adding new targets near existing testing targets.
- Keep names explicit and artifact-oriented.
- Do not silently change the semantics of `make test`.
- If the repo documents a coverage threshold, preserve it.
- After editing, run the new target and confirm the artifact exists before
  rerunning `/crap`.
