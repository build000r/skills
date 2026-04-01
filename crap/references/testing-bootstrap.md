# Testing Bootstrap

Use this reference when `/crap` cannot produce a trustworthy numeric score
because the scope lacks a usable baseline test path, machine-readable coverage
artifacts, or both.

Run the bundled inspector first:

```bash
python3 scripts/inspect_test_stack.py {target}
```

That report tells you whether the current scope is:

- `ready`: tests and machine-readable coverage already exist
- `add-coverage-target`: tests exist, but `/crap` cannot consume them yet
- `bootstrap-tests`: the scope needs a minimal harness before CRAP remediation

## Bootstrap Order

1. Pick the right scope:
   - If repo root is mixed or thin on automation, narrow to the package or crate
     that owns the hotspot and rerun the inspector there.
   - Do not claim the result is repo-wide after narrowing.
2. Establish the baseline test path:
   - Prefer the repo's existing fast path when it already exists.
   - If there is no stable baseline, add the smallest repo-native one first.
3. Add additive machine-readable coverage:
   - Keep `test`, `pytest`, `cargo test`, or the current fast path intact.
   - Add a sibling target or script that writes `coverage.xml` or `lcov.info`.
4. Add one narrow characterization test around the current hotspot frontier:
   - target the function, service, or module currently blocking measurement
   - prefer deterministic fixtures over broad integration scaffolding
5. Only then start the CRAP remediation loop.

## Wrapper Preference

- If the repo already uses `Makefile`, prefer Make targets.
- If the repo does not use `Makefile`, mirror the same behavior in
  `package.json`, `pyproject.toml`-backed tool commands, or `cargo` commands.
- In mixed-language repos, prefer per-ecosystem targets plus an optional
  aggregate `crap` wrapper.

## Python

Use this lane when the scope is Python-first.

Minimum viable bootstrap:

1. Add `pytest` and `pytest-cov` to the test dependency set if missing.
2. Create `tests/` and add one narrow characterization test.
3. Add a baseline test entrypoint, typically `pytest`.
4. Add an additive XML coverage target, typically `pytest-cov-xml`.

Preferred Make targets:

```make
.PHONY: pytest
pytest: ensure-venv
	cd {pkg_dir} && $(ACTIVATE) && pytest {test_path}

.PHONY: pytest-cov-xml
pytest-cov-xml: ensure-venv
	cd {pkg_dir} && $(ACTIVATE) && \
	pytest {test_path} \
	  --cov={coverage_source} \
	  --cov-report=term-missing:skip-covered \
	  --cov-report=xml:coverage.xml
```

Notes:

- Keep the fast path small and repeatable.
- Add `pytest-xdist` only if the repo already leans on parallel pytest runs.
- Characterization tests are enough at bootstrap time; full suite architecture
  can come later.

## TypeScript

Use this lane when the scope is TypeScript-first.

Minimum viable bootstrap:

1. Add `vitest` plus one coverage provider package if missing.
2. Create one `.test.ts` or `.spec.ts` file around the hotspot.
3. Add a baseline test entrypoint.
4. Add an additive lcov-producing coverage entrypoint.

Preferred `package.json` scripts:

```json
{
  "scripts": {
    "test": "vitest run",
    "test:cov": "vitest run --coverage.enabled true --coverage.reporter=lcov --coverage.reporter=text"
  }
}
```

Preferred Make wrapper when the repo already uses `Makefile`:

```make
.PHONY: vitest-cov-lcov
vitest-cov-lcov:
	cd {package_dir} && npm run test:cov
```

Notes:

- Keep the default `test` script free of coverage flags.
- Use the smallest focused test file that proves the hotspot path.

## Rust

Use this lane when the scope is Rust-first.

Minimum viable bootstrap:

1. Add one narrow unit or integration test around the hotspot.
2. Use `cargo test` as the stable baseline.
3. Add an additive lcov export via `cargo llvm-cov`.

Preferred Make target:

```make
.PHONY: cargo-cov-lcov
cargo-cov-lcov:
	cd {crate_dir} && cargo llvm-cov --lcov --output-path lcov.info
```

Notes:

- If `cargo llvm-cov` is not installed, install it before the first CRAP rerun.
- Do not replace `cargo test` with the coverage command.

## Divide-and-Conquer Hand-Off

Do not launch hotspot remediation workers until the measurement lane is real.

When using `divide-and-conquer`, treat prerequisite work as an upstream node:

1. baseline test bootstrap or stabilization
2. additive coverage target bootstrap
3. hotspot-specific remediation slices

The first two nodes may be sequential even when later hotspot slices are
parallel.
