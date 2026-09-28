`[ci] ref` now means the commit of a *released* stayfixed tag, where it meant any ref `git
ls-remote` could resolve. `stayfixed doctor`'s `ci-ref` row reports red for a ref no released
tag names, and `doctor` exits 1 on red — so a configuration that was green under the old
reading can be red under this one. The mutable `v1` alias arrives with the first `1.x`
release; from then on it is reported as the opt-in it is, a warning rather than a fault, and until
then it is red, as a tag the public repository does not carry. Nothing is released yet, so no
installation carries the old meaning; this is recorded because it is a redefinition and not an
addition.
