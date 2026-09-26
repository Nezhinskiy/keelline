"""The strict workflow reader, held to YAML where it reads and to a refusal where it does not.

Every workflow test reads `.github/workflows/` through `tests.workflow_yaml`, so a reader that
stopped early, or skipped a line it could not read, would make every one of them report clean
over the lines it missed. These cases are that reader's own: what ends a block, what is
refused, and a cross-check against `run_blocks`, the independent indentation reader the
expression-injection scan uses.
"""

from __future__ import annotations

import re

import pytest

from tests.test_fixtures import WORKFLOWS, needs_workflows_dir, run_blocks
from tests.workflow_yaml import Node, WorkflowYamlError, load


def _first_step(document: Node) -> dict[str, Node]:
    assert isinstance(document, dict)
    jobs = document["jobs"]
    assert isinstance(jobs, dict)
    job = jobs["one"]
    assert isinstance(job, dict)
    steps = job["steps"]
    assert isinstance(steps, list) and isinstance(steps[0], dict)
    return steps[0]


ENV_HEAD = "jobs:\n  one:\n    steps:\n      - name: a step\n        env:\n          FIRST: one\n"


@pytest.mark.parametrize("indent", [0, 4, 7, 8, 10, 12])
def test_a_comment_or_a_blank_line_never_ends_a_block(indent: int) -> None:
    # YAML ends a block at the first line of content that is not indented past its key, and a
    # comment is never content. The `env:` reader this replaced ended at the first comment it
    # met, so a key written after one was in no assertion: `BASH_ENV` after a comment at eight
    # spaces passed every case. Mutation (declared): a comment line counts as content.
    text = ENV_HEAD + " " * indent + "# a note\n\n          SECOND: two\n        run: echo\n"
    step = _first_step(load(text))
    assert step == {"name": "a step", "env": {"FIRST": "one", "SECOND": "two"}, "run": "echo"}


def test_a_key_written_twice_in_one_mapping_is_refused() -> None:
    # Whatever GitHub does with a duplicate, a reader that kept one of the two let the other
    # pass unseen: a `PYTHONPATH` into the checkout first and the good one last read as the good
    # one. Mutation (declared): the duplicate check is removed.
    with pytest.raises(WorkflowYamlError, match="twice"):
        load(ENV_HEAD + "          FIRST: again\n")


@pytest.mark.parametrize(
    ("tail", "why"),
    [
        pytest.param("          SECOND: {a: b}\n", "a value this reader", id="flow-mapping"),
        pytest.param("          SECOND: &anchor two\n", "a value this reader", id="anchor"),
        pytest.param("          SECOND: *anchor\n", "a value this reader", id="alias"),
        pytest.param("          SECOND: !tag two\n", "a value this reader", id="tag"),
        pytest.param(
            "          SECOND: >\n            folded\n", "a value this reader", id="folded"
        ),
        pytest.param('          "SECOND": two\n', "not a plain key", id="quoted-key"),
        pytest.param(
            "          SECOND: two\n            continued\n",
            "continues on the next line",
            id="plain-continued",
        ),
        pytest.param(
            "          SECOND:\n              DEEP: two\n            MIDDLE: two\n",
            "nothing can own it",
            id="orphan-indentation",
        ),
        pytest.param("          SECOND: a: b\n", "reads as a mapping", id="plain-reads-as-mapping"),
        pytest.param("\tSECOND: two\n", "a tab", id="tab"),
        pytest.param("          -KEY: two\n", "not a plain key", id="not-a-key"),
    ],
)
def test_a_shape_outside_the_subset_is_refused_naming_its_line(tail: str, why: str) -> None:
    # Refused rather than skipped: a shape this reader does not read is a red test in front of
    # whoever wrote it, never a line passed over. Each refusal is its own: a continued plain
    # scalar with its refusal removed is still refused, as a line nothing owns, and a case that
    # asked only for "some refusal" would not see which guard had gone. Mutations (declared):
    # the plain-continuation and orphan-indentation refusals are removed.
    with pytest.raises(WorkflowYamlError, match=rf"line \d+: .*{re.escape(why)}"):
        load(ENV_HEAD + tail)


def test_a_literal_block_ends_at_a_line_indented_less_even_a_comment() -> None:
    # A literal block's indentation is its first non-blank line's; a blank line inside it is
    # kept, and it ends at the first non-blank line indented less, a comment included. Mutation
    # (declared): the block does not end at a line indented less, and swallows the next key.
    text = (
        "jobs:\n  one:\n    steps:\n      - name: a step\n        run: |\n\n"
        "          first\n\n            indented\n        # a note\n        env:\n"
        "          KEY: value\n"
    )
    step = _first_step(load(text))
    assert step["run"] == "\nfirst\n\n  indented\n", step
    assert step["env"] == {"KEY": "value"}, step


def _runs(node: Node) -> list[Node]:
    """Every value of every `run` key in the document, at any depth, in document order."""
    found: list[Node] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "run":
                found.append(value)
            found.extend(_runs(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_runs(item))
    return found


@needs_workflows_dir
def test_every_workflow_reads_whole_and_agrees_with_the_run_scan() -> None:
    # Two readers of one file, built on different rules, cross-checked: the strict reader's
    # `run` values and `run_blocks`' indentation rule must find the same keys, and each script
    # the reader returns must be what the scan collected for it, line for line. A reader that
    # stopped early, or read a script as ending where it does not, disagrees here.
    workflows = sorted(WORKFLOWS.glob("*.y*ml"))
    assert len(workflows) >= 5, workflows
    for workflow in workflows:
        runs = _runs(load(workflow.read_text(encoding="utf-8")))
        blocks = run_blocks(workflow)
        assert len(runs) == len(blocks), (workflow.name, len(runs), len(blocks))
        for run, block in zip(runs, blocks, strict=True):
            if not isinstance(run, str):
                continue  # `defaults: run:`, a mapping, which the scan collects as text
            scanned = [line.strip() for line in block.splitlines() if line.strip() not in ("|", "")]
            read = [line.strip() for line in run.splitlines() if line.strip()]
            assert read == scanned, (workflow.name, read[:3], scanned[:3])
