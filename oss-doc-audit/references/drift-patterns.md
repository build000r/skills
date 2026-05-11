# Common Drift Patterns

Use this file when the first audit pass found more issues than expected or when
the skill needs a sharper second pass.

## High-Signal Patterns

- Docs present a missing route as live.
- Docs present a `501 not implemented` stub as shipped.
- Docs use a deprecated route path after a framework migration.
- Payload examples include fields the active schema does not accept.
- Workflow docs reference nonexistent CI files or status checks.
- Validator scripts still target the deprecated tree after a stack migration.
- README, package manifest, and repo license disagree on public posture.
- Active docs include real IPs, local paths, or internal-only deployment values.

## Fabrication Smells

Distinct from drift: drift is "this was true once, the code moved on."
Fabrication is "this was never true." LLM-assisted doc generation produces
these at scale when the author doesn't verify claims against reality. Every
one of these is a Tier 1 finding — they mislead readers regardless of prose
quality.

### Fabricated compliance claims

Docs that assert SOC2, ISO27001, PCI-DSS, HIPAA, GDPR certification or
"compliance" without the repo actually holding any of those. Often paired
with fake audit dates, fake auditor names, and fake contact phone numbers.

Detection:

```bash
rg -l 'SOC\s*2|ISO\s*27001|PCI[- ]DSS|HIPAA compliant' docs/
rg -n '(compliance|certification|audit)@' docs/
rg -n '\+1[ -]?\(?[0-9]{3}\)?[ -][0-9]{3}[ -][0-9]{4}' docs/  # fake phone numbers
```

Proof step: check for a real audit report, a real certifying body, or a real
legal review in the repo. If none exists, the claim is fabricated.

Real example: `docs/guides/compliance-legal.md` (732 lines) — fabricated
SOC2/ISO27001/PCI certs, nonexistent compliance API endpoints, fake contact
phone numbers.

### Fabricated benchmarks

Performance docs with specific-sounding numbers (p50/p95/p99 latencies, RPS,
concurrent connection counts, regional latency tables) that were never
measured. Telltales: round numbers, implausible scale for the stack,
no benchmark script in the repo, no link to a reproducible harness.

Detection:

```bash
rg -n 'p95|p99|req/s|req/sec|requests per second|concurrent' docs/
rg -n '[0-9]+ ?ms (median|average|p[0-9]+)' docs/
```

Proof step: look for `benchmarks/`, `perf/`, or a benchmark CI workflow. If
none, the numbers are invented.

Real example: `docs/guides/performance-scaling.md` — claimed 23ms median,
50k req/s, 10M concurrent connections, with a regional latency table. No
benchmark script existed in the repo.

### Fictional pricing and competitor comparisons

Pricing pages, billing docs, or "how we compare to X" tables invented without
a real pricing model, real billing endpoints, or real competitor research.

Detection:

```bash
rg -n '\$[0-9]+/month|pricing tier|free tier|enterprise tier' docs/
rg -n 'compared to|vs\.|competitors' docs/
```

Proof step: check for billing code, Stripe product config, or a pricing page
on the real marketing site. If the pricing only exists in docs, it's fiction.

Real example: `docs/guides/cost-billing.md` — invented pricing tiers,
nonexistent billing endpoints, fabricated competitor comparison table.

### Dead-stack code references

Code samples, API examples, or file-path references targeting a deprecated
stack after a migration. The docs look plausible but instruct readers to
modify code that no longer runs.

Detection: grep for deprecated stack markers that the repo's own `CLAUDE.md`
or `AGENTS.md` flags as retired. Example patterns after a Node→Python
migration:

```bash
rg -n 'src/utils/.*\.ts|express|supabase|RLS|auth\.uid\(\)|auth\.users' docs/
```

Proof step: open the referenced file path. If it's in the deprecated tree or
doesn't exist, the doc is targeting dead code.

Real example: `docs/security/SECURITY_IMPLEMENTATION_GUIDE.md` — every code
reference pointed at `src/utils/jwt.ts` and Express middleware after the
repo had migrated to Python/FastAPI. Following the guide would have modified
dead code with zero production effect.

### Fake contact information

Support emails, phone numbers, office addresses, or escalation contacts that
don't exist. Often appears in compliance, security, or "enterprise" docs.

Detection:

```bash
rg -n '(support|security|legal|privacy|compliance)@[a-z]+\.(com|io|dev)' docs/
rg -n '[0-9]{3}[ -][0-9]{3}[ -][0-9]{4}' docs/
```

Proof step: check the real marketing site or company README for actual
contact info. If the doc's contact differs, it's invented.

## Why fabrication is Tier 1

A stale doc wastes reader time. A fabricated doc produces false confidence in
the reader and, in the case of compliance and security claims, creates legal
exposure. Never downgrade fabrication findings to "needs polish" — they get
deleted or rewritten from scratch against verified sources.

For prose-level cleanup (emdashes, forced enthusiasm, "Here's why"
constructions) on the Tier 6/7 docs that survive, hand off to the
`de-slopify` skill. That skill's `references/PATTERNS.md` now also
carries a fabrication cross-reference pointing back here.

## Proof Strategy

For each suspected issue:

1. Open the doc that makes the claim.
2. Open the implementation or schema that proves the claim wrong.
3. Record the exact mismatch, not a vague “stale” label.

## Remediation Bias

When the drift is large, prefer one of these over incremental tweaks:

- replace the doc with a short current-status stub
- move the doc out of the active surface
- point readers at the real source of truth until a full rewrite exists
