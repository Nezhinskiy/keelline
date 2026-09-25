"""Which principle each gate cites, pinned to the principle's title rather than to its number."""

from __future__ import annotations

from keelline.assess.gates import BUILTIN
from tests.test_documents import principle_sections


def test_each_gate_cites_the_principle_it_means() -> None:
    # A number alone would survive the principles being renumbered or retitled under it; the
    # title is what the citation means. `docs` checks budgets and links, which is no principle's
    # own rule, and neither is `commit`'s or `trail`'s. Mutations (advisory): `docs` citing 4,
    # and retitling heading 1 with every number left alone — each reddens.
    titles = {int(number): title for number, title, _body in principle_sections()}
    cited = {gate.name: titles[gate.principle] for gate in BUILTIN if gate.principle is not None}
    assert cited == {
        "bugs": "A bug is a file, and its index is a rendering",
        "plan": "An assertion nobody has watched fail advertises coverage it may not have",
    }
