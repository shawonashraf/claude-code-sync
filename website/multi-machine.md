# Multi-machine

Back up from your laptop and your desktop into the same repo, and sooner or
later they'll disagree. claude-sync's rule for that moment: **it never
merges on its own, and nothing is lost either way.**

## How divergence happens

Machine A backs up and pushes. Machine B, offline that day, backs up too.
Now the shared repo has two histories. The next time B fetches, its backup
repo is *diverged*: both sides have commits the other lacks.

## What claude-sync does about it

Before every backup in git mode, claude-sync checks the destination repo
for divergence or an unfinished merge. What happens next depends on who's
asking:

- **A hook-triggered (quiet) backup** never guesses. It skips the sync,
  leaves the repo untouched, and records a pending conflict.
  `claude-sync status` shows it prominently:

  ```text
  CONFLICT PENDING: run claude-sync resolve to choose a version
  ```

- **You, interactively** (`claude-sync resolve`, or any manual `backup`)
  get the actual decision, stated plainly:

  > Your backup has two conflicting versions: this machine's and the one in
  > the repo. Keeping one loses the other from the working copy — the
  > losing version stays in git history.

  - **Keep this machine's version** — the repo is brought to a clean state,
    then overwritten with a fresh mirror of this machine's settings. Done;
    this machine wins.
  - **Keep the repo's version** — the repo adopts the other machine's
    version, and this backup is skipped. Run `claude-sync restore` right
    after to adopt it locally too.
  - **Cancel** — nothing is touched; the conflict stays pending.

Either resolution creates a proper merge commit, so the version you didn't
pick remains one `git log` away. Peace of mind is the point: choosing wrong
costs you a `git checkout`, not your setup.

## auto_push

With `"auto_push": true` in `~/.claude-sync.json`, every backup commit is
pushed immediately — which keeps machines convergent, because each one sees
the others' backups sooner. Push failures never fail a backup; you get a
one-line warning and the push retries next time.

Next: [exactly what leaves your machine →](security.md)
