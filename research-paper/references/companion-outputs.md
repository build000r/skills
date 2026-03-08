# Companion Output Structure

Every research-paper run produces two artifacts:

1. A canonical research paper
2. A companion X article

The paper is the source of truth. The X article is a derivative compression. It may simplify framing and pacing, but it must not introduce unsupported claims.

## Generation Order

1. Finish the research and canonical paper first.
2. Derive the X article from the paper.

## Companion X Article

### Goal

Turn the paper into a faster, more readable piece for the X Articles composer while preserving the core argument and best evidence.

### Default Format

- Markdown or plain text by default
- 1,000-2,500 words unless the mode says otherwise
- One title and optional subtitle/deck
- Four to seven sections
- Shorter paragraphs than the paper
- At most one table or framework visual in the default version
- Easy to paste into [X Articles](https://x.com/compose/articles/edit) with minimal cleanup

### Content Rules

- Keep the same thesis as the paper.
- Lead with the strongest why-now angle, not the full literature review.
- Reuse the best numbers and citations from the paper.
- Cut repetition, taxonomy sprawl, and low-signal caveats.
- End with a short synthesis and, when relevant, a pointer to the full paper.
- Avoid Markdown features that usually need hand-fixing in a WYSIWYG editor.
- Prefer clean headings, short paragraphs, short lists, and inline links.

### Default X Article Structure

1. **Title**: Clear promise, less academic than the paper if needed
2. **Lede**: 2-4 paragraphs explaining the problem, why it matters now, and the thesis
3. **What the evidence says**: The strongest data points and case studies
4. **Why the mainstream view misses it**: Contrarian or corrective angle
5. **Framework**: One practical model, decision rule, or taxonomy
6. **Implications**: What builders/practitioners should do differently
7. **Conclusion**: Tight summary plus optional pointer to the full paper

### Self-Check

Reject and rewrite the X article if:

- The opening could fit any topic with a few nouns swapped
- There are no concrete numbers or named examples
- The draft contains scaffolding text the user would have to delete before pasting
- The formatting depends on advanced Markdown that the composer may flatten awkwardly
