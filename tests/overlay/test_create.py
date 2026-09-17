from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from keelline.errors import Failure, Refusal
from keelline.overlay.api import Completed, create, init_instance
from keelline.overlay.create import RETRY_WAIT_SECONDS


@dataclass
class FakeRunner:
    """Records argv and answers from a script, so every assertion is about the command run."""

    answers: dict[str, Completed] = field(default_factory=dict)
    calls: list[list[str]] = field(default_factory=list)
    on_call: Callable[[list[str], Path], None] | None = None

    def run(self, argv: list[str], cwd: Path) -> Completed:
        self.calls.append(argv)
        if self.on_call is not None:
            self.on_call(argv, cwd)
        return self.answers.get(argv[0], Completed(0, "", ""))


def _populate(argv: list[str], cwd: Path) -> None:
    """Stand in for a successful template generation: write the probe `create` looks for."""
    if argv[:3] != ["gh", "repo", "create"]:
        return
    target = cwd / argv[3].split("/")[-1] / ".claude-plugin"
    target.mkdir(parents=True, exist_ok=True)
    (target / "plugin.json").write_text(json.dumps({"name": "keelline-overlay"}), encoding="utf-8")


def test_creating_from_the_template_asks_github_for_a_private_repository(tmp_path: Path) -> None:
    # §6.1 and D1: a template rather than a fork, because a fork's visibility is bound to the
    # upstream network and cannot be made private. The `--private` flag is that decision.
    runner = FakeRunner(on_call=_populate)
    create("octo", "keelline-private", source="template", root=tmp_path, runner=runner)
    assert runner.calls[0][:3] == ["gh", "repo", "create"]
    assert "--private" in runner.calls[0]
    assert "--template" in runner.calls[0]


def test_a_clone_that_raced_generation_is_retried_once_before_failing(tmp_path: Path) -> None:
    # Findings → S6: the race did not reproduce in the one trial that was run, and one clean
    # run cannot rule out an asynchronous generation step that sometimes outlasts the clone.
    # The retry is therefore carried on the strength of the design, not of a measurement — so
    # it is asserted here rather than left to be discovered by whoever hits it.
    empty = FakeRunner()
    with pytest.raises(Failure):
        create("octo", "keelline-private", source="template", root=tmp_path, runner=empty)
    verbs = [argv[:3] for argv in empty.calls]
    assert ["gh", "repo", "view"] in verbs, "must distinguish 'not created' from 'raced'"
    assert ["git", "clone", "--"] in verbs


def test_an_existing_populated_clone_is_left_alone(tmp_path: Path) -> None:
    # §6.1 requires idempotence in as many words, because `gh` "may give up on the clone with
    # the repository already created" — so the second run finds a tree and must not re-create.
    (tmp_path / "keelline-private" / ".claude-plugin").mkdir(parents=True)
    (tmp_path / "keelline-private" / ".claude-plugin" / "plugin.json").write_text(
        "{}", encoding="utf-8"
    )
    runner = FakeRunner()
    created = create("octo", "keelline-private", source="template", root=tmp_path, runner=runner)
    assert runner.calls == []
    assert "exists" in " ".join(created.notes)


def test_the_local_source_touches_no_network(tmp_path: Path) -> None:
    # The documented fallback when the template repository is unreachable, and the only mode a
    # test may exercise end to end.
    runner = FakeRunner()
    created = create("octo", "keelline-private", source="local", root=tmp_path, runner=runner)
    assert runner.calls == []
    assert (created.root / ".claude-plugin" / "plugin.json").is_file()
    assert (created.root / "hooks" / "hooks.json").is_file()


@pytest.mark.parametrize("name", ["../escape", "a/b", "", "-flag"])
def test_a_name_that_is_not_one_path_segment_is_refused(tmp_path: Path, name: str) -> None:
    # §7.4's source rule, applied to a value that becomes a directory name, a remote path and
    # later a marketplace selector. `-flag` is in the list because §3 requires that a
    # configured value shaped like an option never reaches a subprocess in an option's position.
    with pytest.raises(Refusal):
        create("octo", name, source="local", root=tmp_path, runner=FakeRunner())


def test_init_renames_the_plugin_and_marketplace_for_the_owner(tmp_path: Path) -> None:
    # §6.1: "so two overlays never collide". Findings → S6 Step 3 measured that an
    # owner-suffixed pair, pushed to a private SSH remote, was added and installed without
    # error under a scratch CLAUDE_CONFIG_DIR.
    created = create("octo", "keelline-private", source="local", root=tmp_path, runner=FakeRunner())
    init_instance(created.root, "OctoCat", runner=FakeRunner())
    plugin = json.loads((created.root / ".claude-plugin" / "plugin.json").read_text())
    market = json.loads((created.root / ".claude-plugin" / "marketplace.json").read_text())
    assert plugin["name"] == "keelline-overlay-octocat"
    assert market["name"] == "keelline-overlay-marketplace-octocat"


def test_init_installs_pre_commit_and_says_so_when_it_cannot(tmp_path: Path) -> None:
    # §6.4: gitleaks runs twice, and one of the two is this hook. A missing `pre-commit` is a
    # reported finding, never a traceback — the binary is optional by the global constraints.
    created = create("octo", "keelline-private", source="local", root=tmp_path, runner=FakeRunner())
    missing = FakeRunner(answers={"pre-commit": Completed(127, "", "not found")})
    result = init_instance(created.root, "octo", runner=missing)
    assert any("pre-commit" in note for note in result.notes)


def test_init_is_idempotent(tmp_path: Path) -> None:
    created = create("octo", "keelline-private", source="local", root=tmp_path, runner=FakeRunner())
    first = init_instance(created.root, "octo", runner=FakeRunner())
    second = init_instance(created.root, "octo", runner=FakeRunner())
    assert first.renamed != () and second.renamed == ()


def test_the_cli_never_picks_the_github_source_for_you() -> None:
    # Task 6's own rule, which has no other witness: "`--template` is never the default: an
    # invocation with neither flag refuses and names both". §6.1 permits creating a repository
    # on an account only after explicit confirmation, and a non-interactive caller — the usual
    # one in this harness — can express confirmation only by naming the source. Mutation:
    # `source="template"` in that parser's `set_defaults` and this reddens; it is declared in
    # `mutations.toml`, because the failure creates a repository nobody asked for.
    from keelline.cli import build_parser, discover_registrars
    from keelline.overlay.commands import run_overlay_create

    args = build_parser(discover_registrars()).parse_args(["overlay", "create", "--owner", "octo"])
    with pytest.raises(Refusal) as refused:
        run_overlay_create(args)
    assert "--template" in str(refused.value)
    assert "--local" in str(refused.value)


def test_the_wait_before_the_retry_is_spent_only_on_the_race(tmp_path: Path) -> None:
    # "on the second, wait and retry once": the pause exists for an asynchronous generation step
    # that may still be running, so it is spent only when `gh repo view` names the repository
    # back. Spending it when nothing was created is ten seconds bought with nothing, and it is
    # the branch the retry test above never reaches. Mutation: make the wait unconditional and
    # the second half reddens; drop it entirely and the first half does.
    named: list[float] = []
    answering = FakeRunner(answers={"gh": Completed(0, "keelline-private\n", "")})
    with pytest.raises(Failure):
        create(
            "octo",
            "keelline-private",
            source="template",
            root=tmp_path,
            runner=answering,
            wait=named.append,
        )
    assert named == [RETRY_WAIT_SECONDS]

    silent: list[float] = []
    with pytest.raises(Failure):
        create(
            "octo",
            "keelline-private",
            source="template",
            root=tmp_path,
            runner=FakeRunner(),
            wait=silent.append,
        )
    assert silent == []
