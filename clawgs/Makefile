LLVM_COV ?= $(shell xcrun --find llvm-cov 2>/dev/null || command -v llvm-cov 2>/dev/null || true)
LLVM_PROFDATA ?= $(shell xcrun --find llvm-profdata 2>/dev/null || command -v llvm-profdata 2>/dev/null || true)

.PHONY: cargo-cov-lcov
cargo-cov-lcov: ## Run Rust coverage with lcov output for /crap
	@test -n "$(LLVM_COV)" && test -n "$(LLVM_PROFDATA)" || \
		(printf '%s\n' "error: llvm-cov and llvm-profdata are required" >&2; exit 1)
	LLVM_COV="$(LLVM_COV)" LLVM_PROFDATA="$(LLVM_PROFDATA)" \
		cargo llvm-cov --lcov --output-path lcov.info
