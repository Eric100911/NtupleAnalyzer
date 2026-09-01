# IHEP staging monitor target

Use this target contract when the optional IHEP-to-CERN-EOS staging worker is
launched. It is an additional read-only target for the campaign monitor, not a
replacement for Condor or the downstream processing-site target.

The target is bound to the frozen campaign identity and staging plan hash and
contains the IHEP scheduler/worker endpoint, detached PID (or PID file), status
sentinel, persistent log, and declared staged-manifest path. The worker target
is considered `unknown` when its status is absent, its PID disappears without
an exit status, or its query times out. A terminal `complete` state requires a
published staged manifest whose original formal manifest ID/SHA-256 and plan
hash match the frozen state.

The monitor may read scheduler state, worker status, log metadata, and staged
manifest checksums, and may emit an atomic snapshot/alert. It must never start,
stop, retry, kill, clean, or repair the IHEP worker, create EOS directories,
or alter the target configuration. Adding this target requires an atomic target
configuration revision by the orchestrator and a separate staging
authorization. Existing Condor/hepthu monitor behavior remains unchanged until
the monitor implementation explicitly supports this target kind.
