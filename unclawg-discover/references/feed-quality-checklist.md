# Feed Quality Checklist

Run this before presenting or persisting results.

## Intake Quality

- [ ] Objective is explicit and measurable.
- [ ] Persona priority is explicit.
- [ ] Platform scope and paid-query constraints are confirmed.

## Discovery Quality

- [ ] Queries map directly to objective and persona.
- [ ] At least one free-source baseline channel was run (Reddit or HN).
- [ ] Paid channels were approved before execution.
- [ ] X + LinkedIn query windows are set for near-real-time runs (`--days 1` + post-filter by hours).

## Candidate Quality

- [ ] Every candidate has URL + source text.
- [ ] Every candidate has an evidence note.
- [ ] Every candidate maps to one intent signal.
- [ ] Noise/seller posts were filtered before ranking.
- [ ] X + LinkedIn items older than max age (default 6h) are removed.
- [ ] X + LinkedIn ranking is recency-first (0-2h, 2-4h, 4-6h).

## Output Quality

- [ ] Ranked table is included.
- [ ] Top 3 outreach candidates are called out.
- [ ] Top 3 content/influence candidates are called out.
- [ ] Rejected-pattern summary is included.
