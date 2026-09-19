# When a baseline lies

**A baseline reproduction proves only that your change did not cause it.** Two more
questions decide whether it is environmental at all: does it also fail on an idle host
(load-independence means logic), and does the assertion still fail when you inject each
regression it claims to catch (a "flake" that was a wrong assertion pinning a tie-break).

**"Contention" needs the margin computed cold, on the target platform, under load.** A
warm in-process margin is a veto on "load"; a suite running faster on the suspect host
refutes it; red-then-green on a quiet machine changes the sample, not the mechanism. The
class to look for first: a real-time budget racing a lazily-fetched resource in an
ephemeral environment. Making the resource faster is the wrong repair; stop denominating
the test in wall clock.

**Timing comparisons must be interleaved, never sequential**: anything that rebuilds on a
branch switch loads the machine with the switch itself.

**The baseline can lie in two opposite ways, with opposite remedies:**

- A scratch extraction lacks everything the repository does not track — local
  configuration, environment files, caches — so code branching on such a file takes the
  other path. The tell is a uniformly benign "before" column. Remedy: plant the same fixture
  on both sides.
- An in-place baseline shares a poisoned bytecode cache: a long-stashed checkout held
  compiled files newer than their sources, both halves imported pre-fix code, and a defect
  was filed that did not exist. The tell is a red in exactly the shape of an already-fixed
  defect. Remedy: a fresh extraction with its own synced environment, which is what runs 2
  and 3 are.

**The seam has a wall-clock bound.** Each run goes through the same launcher every other
external program does, with its fixed timeout; a suite longer than that is reported as
timed out rather than as failed. Narrow the command to the failing test.
