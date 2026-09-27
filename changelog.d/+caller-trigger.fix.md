The caller workflow `keelline init` writes runs only for pull requests into the gate branch, runs
again when one is retargeted, reports for the gate branch's merge queue and no other branch's, and
passes the gate branch as a literal `base:`. A pull request could otherwise collect a green check
against a looser branch and then be retargeted onto the gate branch. `keelline upgrade` refreshes an
untouched caller when it moves the pin; a hand-edited one is reported `skip_modified`, and `upgrade`
then holds `[keelline] version` and `[ci] ref` until `--force .github/workflows/keelline.yml` or a
hand edit brings the caller in line.
