The mutation oracle no longer writes the working tree. Every declared mutation is applied
to a throwaway checkout of `HEAD`, so two runs — or a run beside an editor — cannot
interleave writes over one file, and an interrupted run leaves nothing to restore.
