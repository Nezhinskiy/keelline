`[ci] ref` now means the commit of a *released* Keelline tag, where it meant any ref `git
ls-remote` could resolve. `keelline doctor`'s `ci-ref` row reports red for a ref no released
tag names, and `doctor` exits 1 on red — so a configuration that was green under the old
reading can be red under this one. The documented mutable `v1` alias is reported as the
opt-in it is rather than as a fault. Nothing is released yet, so no installation carries the
old meaning; this is recorded because it is a redefinition and not an addition.
