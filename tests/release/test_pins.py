from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from keelline import REPOSITORY_URL
from keelline.release.api import Pin, Resolution, is_released, released, resolve_pin
from keelline.runner import NOT_FOUND, Completed

LIGHT, TAG_OBJECT, COMMIT, ALIAS = "1" * 40, "2" * 40, "3" * 40, "9" * 40
LISTING = (
    f"{LIGHT}\trefs/tags/v0.1.0\n"
    f"{TAG_OBJECT}\trefs/tags/v1.0.0\n"
    f"{COMMIT}\trefs/tags/v1.0.0^{{}}\n"
    f"{ALIAS}\trefs/tags/v1\n"
    f"{'4' * 40}\trefs/tags/keelline--v1.0.0\n"
)


@dataclass
class _Stub:
    code: int = 0
    stdout: str = LISTING
    calls: list[list[str]] = field(default_factory=list)

    def run(self, argv: list[str], cwd: Path) -> Completed:
        self.calls.append(argv)
        return Completed(self.code, self.stdout, "")


def test_an_annotated_tag_resolves_to_its_commit_not_its_tag_object(tmp_path: Path) -> None:
    # Mutation (oracle): `{**peeled, **plain}` -> the annotated case answers the tag object,
    # which a workflow pin could not check out.
    stub = _Stub()
    assert resolve_pin("1.0.0", stub, cwd=tmp_path) == Resolution(Pin("v1.0.0", COMMIT), True)
    assert resolve_pin("0.1.0", stub, cwd=tmp_path) == Resolution(Pin("v0.1.0", LIGHT), True)
    assert len(stub.calls) == 2
    assert stub.calls[0] == ["git", "ls-remote", "--exit-code", REPOSITORY_URL, "refs/tags/v*"]


def test_the_three_answers_stay_apart(tmp_path: Path) -> None:
    # "no such tag", "no tags at all" and "git could not answer" are three sentences in
    # `init`'s report and two statuses in `doctor`; `Resolution.asked` is what keeps the third
    # apart from the first two.
    assert resolve_pin("9.9.9", _Stub(), cwd=tmp_path) == Resolution(None, True)
    assert resolve_pin("0.1.0", _Stub(code=2, stdout=""), cwd=tmp_path) == Resolution(None, True)
    assert resolve_pin("0.1.0", _Stub(code=NOT_FOUND, stdout=""), cwd=tmp_path) == Resolution(
        None, False
    )
    assert released(_Stub(code=128, stdout=""), cwd=tmp_path) is None


def test_is_released_judges_semver_tags_and_never_the_alias(tmp_path: Path) -> None:
    assert is_released(LIGHT, _Stub(), cwd=tmp_path) is True
    assert is_released(COMMIT, _Stub(), cwd=tmp_path) is True
    assert is_released(ALIAS, _Stub(), cwd=tmp_path) is False
    assert is_released("5" * 40, _Stub(code=2, stdout=""), cwd=tmp_path) is False
    assert is_released(LIGHT, _Stub(code=NOT_FOUND, stdout=""), cwd=tmp_path) is None
    pins = released(_Stub(), cwd=tmp_path)
    assert pins is not None
    assert "v1" in pins
