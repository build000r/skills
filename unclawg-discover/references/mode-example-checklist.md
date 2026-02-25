# Mode Example with Ask-Cascade Checklist

Use this as a quality blueprint when writing your local `modes/<project>.md` file.

## Ask-Cascade Checklist

- [ ] Question 1 (strategic): "What is this run for: prospects, content, or influence?"
- [ ] Question 2 (strategic): "Which persona is highest priority for this run?"
- [ ] Question 3 (constraints): "What channels are in scope and what paid-query budget is allowed?"
- [ ] Question 4 (execution): "How many final candidates do you want, and how strict should filtering be?"
- [ ] Question 5 (handoff): "Where should this feed go next (command/system), and what schema is required?"

## Feed Quality Checklist

- [ ] At least 60% of final candidates have explicit user pain in first-person language.
- [ ] At least 80% include a valid source URL and extractable context text.
- [ ] Duplicate or near-duplicate posts are removed.
- [ ] Vendor/seller noise is under 20% before final ranking.
- [ ] Top 3 candidates include a clear evidence note and next-action recommendation.

## Example Handoff Section

```yaml
handoff_command: /unclawg-feed
required_fields:
  - source_platform
  - source_post_url
  - source_post_text
  - summary
  - action
  - reply_strategy
```
