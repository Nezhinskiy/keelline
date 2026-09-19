from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import NoReturn

import pytest

from keelline.errors import Failure, Refusal
from keelline.overlay.api import create, init_instance
from keelline.overlay.create import RETRY_WAIT_SECONDS
from keelline.runner import Completed


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
    # "did not run" and not merely "pre-commit": the success note names the tool too, so the
    # weaker match held on either outcome and this half asserted nothing.
    assert any("`pre-commit install` did not run" in note for note in result.notes)
    assert not any("installed the commit-time" in note for note in result.notes)


def test_init_refuses_a_directory_that_is_not_an_overlay_before_touching_it(
    tmp_path: Path,
) -> None:
    # `--root` defaults to `.`, and `init` asked nothing of it: run inside the Keelline checkout
    # itself, it renamed all three plugin manifests and installed a commit hook there. `upgrade`
    # had the guard and `setup` uses it twice; this is the caller `identity.py` was written for
    # that it did not list. Mutation: the `require_overlay` line removed → the manifest below is
    # renamed and the runner is called.
    project = tmp_path / "project"
    (project / ".claude-plugin").mkdir(parents=True)
    manifest = project / ".claude-plugin" / "plugin.json"
    manifest.write_text(json.dumps({"name": "somebody-elses-plugin"}), encoding="utf-8")
    runner = FakeRunner()
    with pytest.raises(Refusal) as refused:
        init_instance(project, "octo", runner=runner)
    assert "overlay init" in str(refused.value)
    assert json.loads(manifest.read_text())["name"] == "somebody-elses-plugin"
    assert runner.calls == []


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


def test_a_render_that_cannot_start_leaves_no_probe_behind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The directory `--local` has to create first is `<name>/.claude-plugin`, which is exactly
    # the probe `--template` reads as "this was already created". So a `--local` that refused
    # after creating it would leave the owner in the one state where the honest recovery —
    # `overlay create --template` — reports "already exists and was left alone" and never
    # creates the repository at all. Everything that can refuse therefore runs first. Mutation:
    # move the `plan(...)` call back below `mkdirs_within` and this reddens on the second
    # assertion, with a directory on disk and no repository anywhere.
    def _unavailable() -> NoReturn:
        raise Failure("this Keelline was installed without the template tree")

    monkeypatch.setattr("keelline.overlay.create.templates", _unavailable)
    with pytest.raises(Failure):
        create("octo", "keelline-private", source="local", root=tmp_path, runner=FakeRunner())
    assert not (tmp_path / "keelline-private").exists()


def test_a_mixed_case_owner_gets_one_answer_from_both_commands(tmp_path: Path) -> None:
    # `SEGMENT` has a lowercase leading class and a mixed-case GitHub login is ordinary, so the
    # two commands have to fold alike. `create` validated the raw value while `init_instance`
    # folded first, which refused `--owner OctoCat` from the wave's headline command and
    # accepted it from the other — one owner string, two answers, and a refusal saying "is not
    # one path segment" about a value that is one. Mutation: validate `owner` rather than
    # `account` in `create` and the first half reddens with a `Refusal`.
    remote = tmp_path / "remote"
    remote.mkdir()
    runner = FakeRunner(on_call=_populate)
    create("OctoCat", "keelline-private", source="template", root=remote, runner=runner)
    # And the fold reaches the argv, not just the validator: GitHub is case-insensitive about a
    # login, but the value is also a directory name and a manifest suffix, and those are not.
    assert "octocat/keelline-private" in runner.calls[0]

    local = tmp_path / "local"
    local.mkdir()
    created = create("OctoCat", "keelline-private", source="local", root=local, runner=FakeRunner())
    init_instance(created.root, "OctoCat", runner=FakeRunner())
    plugin = json.loads((created.root / ".claude-plugin" / "plugin.json").read_text())
    assert plugin["name"] == "keelline-overlay-octocat"


def test_a_gh_that_is_not_installed_is_named_as_the_cause_and_costs_one_subprocess(
    tmp_path: Path,
) -> None:
    # Review finding 4. `Completed` has carried `code` and `stderr` since this seam was written
    # and this lane threw both away: with `gh` absent from `PATH`, the command launched three
    # subprocesses and then exited 1 saying "GitHub did not confirm the repository exists; check
    # `gh auth status`" — a cause that was not the cause, about a binary that was not there.
    # A missing optional binary is a reported finding, and never a misattributed one.
    #
    # Mutation (`mutations.toml`, "overlay create --template asks GitHub about a `gh` that
    # could not run"): the `NOT_FOUND`/`TIMED_OUT` arm becomes `if False:` → two more
    # subprocesses run and the message names `gh auth status` instead of the launch failure.
    absent = FakeRunner(answers={"gh": Completed(127, "", "gh could not be run: [Errno 2] gh")})
    waited: list[float] = []
    with pytest.raises(Failure) as failed:
        create(
            "octo",
            "keelline-private",
            source="template",
            root=tmp_path,
            runner=absent,
            wait=waited.append,
        )
    message = str(failed.value)
    assert "gh could not be run" in message, "the real cause is in Completed.stderr"
    assert "gh auth status" not in message, "a binary that never ran cannot have a bad token"
    assert "--local" in message, "the source that works today has to be named"
    # The sentence only this arm produces. `Runner`'s own docstring keeps "not installed" and
    # "hung for five minutes" apart because their remedies differ, and without this assertion
    # the mutation below survives: the next arm — `gh` ran and declined — quotes the same
    # stderr and stops after the same one call, so every other assertion here holds under it.
    assert "Install `gh` and authenticate it" in message
    assert [argv[:3] for argv in absent.calls] == [["gh", "repo", "create"]]
    assert waited == [], "nothing was waiting to finish generating"


def test_a_gh_that_ran_and_declined_quotes_its_own_answer(tmp_path: Path) -> None:
    # The other arm of the same finding, and the one `docs/cli.md` names as the actual reason
    # `--template` cannot work today: `<owner>/keelline-overlay-template` does not exist,
    # because the maintainer action that would publish it has not shipped. `gh`'s own stderr
    # says so, and is quoted rather than replaced by a guess about authentication.
    declined = FakeRunner(
        answers={"gh": Completed(1, "", "GraphQL: Could not resolve to a Repository")}
    )
    with pytest.raises(Failure) as failed:
        create("octo", "keelline-private", source="template", root=tmp_path, runner=declined)
    message = str(failed.value)
    assert "Could not resolve to a Repository" in message
    assert "nothing publishes that repository yet" in message
    assert "exited 1" in message, "a binary that ran has an exit code, not a launch failure"
    assert [argv[:3] for argv in declined.calls] == [["gh", "repo", "create"]]


def test_init_names_the_codex_manifest_after_the_owner_too(tmp_path: Path) -> None:
    # Review finding 16. `init_instance`'s own docstring gives the rationale — a harness
    # installs a plugin by the name in its manifest, so two owners' overlays under one
    # configuration directory are one plugin fighting itself — and the project ships a Codex
    # half of everything else, but `.codex-plugin/plugin.json` was left unsuffixed, so the
    # collision the suffix exists to prevent still happened on Codex.
    #
    # Mutation (`mutations.toml`, "overlay init leaves the Codex manifest unsuffixed"):
    # `CODEX_PLUGIN_MANIFEST` is dropped from `MANIFESTS` → this reddens on the third name.
    created = create("octo", "keelline-private", source="local", root=tmp_path, runner=FakeRunner())
    init_instance(created.root, "OctoCat", runner=FakeRunner())
    names = {
        relative: json.loads((created.root / relative).read_text(encoding="utf-8"))["name"]
        for relative in (
            ".claude-plugin/plugin.json",
            ".claude-plugin/marketplace.json",
            ".codex-plugin/plugin.json",
        )
    }
    assert names == {
        ".claude-plugin/plugin.json": "keelline-overlay-octocat",
        ".claude-plugin/marketplace.json": "keelline-overlay-marketplace-octocat",
        ".codex-plugin/plugin.json": "keelline-overlay-octocat",
    }


def test_a_manifest_this_overlay_does_not_carry_is_a_note_not_a_failure(tmp_path: Path) -> None:
    # An overlay generated before the Codex half shipped carries two of the three manifests,
    # and refusing to name the other two over it would make `init` unusable on exactly the
    # overlays that most need running it. A manifest that *exists* and cannot be read is still
    # a failure — that is a file saying something this command cannot act on.
    created = create("octo", "keelline-private", source="local", root=tmp_path, runner=FakeRunner())
    (created.root / ".codex-plugin" / "plugin.json").unlink()
    result = init_instance(created.root, "octo", runner=FakeRunner())
    assert ".codex-plugin/plugin.json" not in result.renamed
    assert any(".codex-plugin/plugin.json" in note for note in result.notes)
