import json
import re
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest import mock


MODULE = SourceFileLoader(
    "br_to_mmdx",
    str((Path(__file__).resolve().parent.parent / "scripts" / "br_to_mmdx.py").resolve()),
).load_module()


class BrToMmdxTests(unittest.TestCase):
    def test_br_list_delegates_to_shared_br_helper(self) -> None:
        repo = Path("/repo")
        with mock.patch.object(MODULE.br_helpers, "list_issues", return_value=[{"id": "bd-1"}]) as list_issues:
            issues = MODULE.br_list(repo, ["chain:smart", "loop:alpha"])

        self.assertEqual(issues, [{"id": "bd-1"}])
        list_issues.assert_called_once_with(
            cwd=repo,
            labels=["chain:smart", "loop:alpha"],
            include_closed=True,
        )

    def test_render_mmdx_matches_golden_chain_stack(self) -> None:
        loop = MODULE.Loop(
            loop_id="smart",
            repo="repo",
            links=[
                MODULE.Link(
                    issue_id="bd-1",
                    title="First link",
                    status="closed",
                    created_at="2026-06-01T12:00:00-0700",
                    updated_at="2026-06-01T14:00:00-0700",
                    labels=["loop:smart", "loop-status:done"],
                    loop_status="done",
                ),
                MODULE.Link(
                    issue_id="bd-2",
                    title="Second link",
                    status="done",
                    created_at="2026-06-01T15:00:00-0700",
                    updated_at="2026-06-01T15:30:00-0700",
                    labels=["loop:smart"],
                ),
            ],
        )

        expected = """<!-- mmdx
{
  "entry": "main",
  "links": [
    {
      "from": "main",
      "label": "repo \\u00b7 smart",
      "to": "loop_repo_smart",
      "title": "Open repo smart (2 links, closed)"
    }
  ]
}
-->

## chart main BR Chain (1 loops)
```mermaid
gantt
  title BR Chain \u2014 2 links across 1 loops
  dateFormat  YYYY-MM-DD HH:mm
  axisFormat  %b %d

  section repo \u00b7 smart
  First link  :done, repo_smart_0, 2026-06-01 12:00, 2h
  Second link  :done, repo_smart_1, 2026-06-01 15:00, 1h

```

## chart loop_repo_smart repo \u00b7 smart
```mermaid
flowchart TD
  l0["First link<br/><b>done</b><br/><i>2026-06-01 12:00</i>"]:::done
  l1["Second link<br/><b>done</b><br/><i>2026-06-01 15:00</i>"]:::done
  l0 --> l1
  classDef open fill:#fde68a,stroke:#b45309,color:#1c1917
  classDef blocked fill:#fecaca,stroke:#991b1b,color:#1c1917
  classDef done fill:#bbf7d0,stroke:#166534,color:#1c1917
  classDef resume fill:#dbeafe,stroke:#1e40af,color:#1e3a8a,stroke-dasharray: 4 2
```
"""

        self.assertEqual(MODULE.render_mmdx([loop]), expected)

    def test_render_loop_drilldown_escapes_user_controlled_mermaid_text(self) -> None:
        loop = MODULE.Loop(
            loop_id="smart",
            repo="repo",
            links=[
                MODULE.Link(
                    issue_id="bd-1",
                    title='Close label"] --> injected\n<script>',
                    status="open",
                    created_at="2026-06-01T12:00:00-0700",
                    updated_at="2026-06-01T12:00:00-0700",
                    labels=["loop:smart", 'loop-status:waiting"now'],
                    resume_condition='quote"] and <tag>',
                    loop_status='waiting"now',
                ),
            ],
        )

        rendered = MODULE.render_loop_drilldown(loop)

        self.assertIn("Close label&quot;] --&gt; injected &lt;script&gt;", rendered)
        self.assertIn("<b>waiting&quot;now</b>", rendered)
        self.assertIn("quote&quot;] and &lt;tag&gt;", rendered)
        self.assertNotIn('label"] --> injected', rendered)
        self.assertNotIn('quote"]', rendered)

    def test_render_mmdx_disambiguates_colliding_normalized_loop_ids(self) -> None:
        loops = [
            MODULE.Loop(
                loop_id="a-b",
                repo="repo",
                links=[
                    MODULE.Link(
                        issue_id="bd-1",
                        title="First loop",
                        status="open",
                        created_at="2026-06-01T12:00:00-0700",
                        updated_at="2026-06-01T12:00:00-0700",
                        labels=["loop:a-b"],
                    )
                ],
            ),
            MODULE.Loop(
                loop_id="a_b",
                repo="repo",
                links=[
                    MODULE.Link(
                        issue_id="bd-2",
                        title="Second loop",
                        status="open",
                        created_at="2026-06-01T13:00:00-0700",
                        updated_at="2026-06-01T13:00:00-0700",
                        labels=["loop:a_b"],
                    )
                ],
            ),
        ]

        rendered = MODULE.render_mmdx(loops)
        metadata = json.loads(re.search(r"<!--\s*mmdx\s*(\{.*?\})\s*-->", rendered, re.DOTALL).group(1))
        link_targets = [link["to"] for link in metadata["links"]]
        chart_ids = re.findall(r"^## chart ([A-Za-z0-9_-]+)", rendered, re.MULTILINE)
        gantt_task_ids = re.findall(r":active, ([^,]+), 2026-06-01", rendered)

        self.assertEqual(len(link_targets), len(set(link_targets)))
        self.assertTrue(all(target.startswith("loop_repo_a_b_") for target in link_targets))
        self.assertEqual(sorted(link_targets), sorted(chart_ids[1:]))
        self.assertEqual(len(gantt_task_ids), len(set(gantt_task_ids)))


if __name__ == "__main__":
    unittest.main()
