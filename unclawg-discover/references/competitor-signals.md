# Exclusion Signals (Generic)

Filter out noise before ranking. This saves tokens and improves feed quality.

## Auto-Exclude Patterns

### Vendor / Seller Signals

- Profile says founder/CEO/devrel at a company selling the same solution.
- Post is an announcement thread for their own product launch.
- Repeated CTA language: "book a demo", "try our platform", "DM for pricing".
- Replies contain mostly promotional links.

### Recruiter / Aggregator Noise

- Generic job spam with no real problem context.
- Account repeatedly reposts job listings or scraped content.
- "Thought leader" posts with no actionable details.

### Low-Evidence Content

- Missing source URL or inaccessible source.
- Text too short to infer user intent.
- Obvious AI-generated engagement bait with no real scenario.

## Keep Patterns

- First-person pain statements with concrete details.
- Specific constraints, timeline, or budget signals.
- Direct requests for recommendations.
- Follow-up comments showing continued intent.

## Borderline Cases

Keep in review queue (do not auto-reject):

- Consultants/analysts discussing a real implementation problem.
- Technical maintainers asking for guidance, not selling.
- Journalists with verified incident sourcing that can drive visibility.
