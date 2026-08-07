# Branch protection — owner action required

The new CI does **not** re-run the complete suite after a merge to `main`. That
saving is only safe once `main` is protected. This page is the checklist, and it
is an owner action: it cannot be done from a workflow or by an agent.

## Why the post-merge full suite was removed

A `pull_request` workflow does not test your branch. It tests GitHub's synthetic
**merge result** — your branch already merged into the base. When that PR is
merged with a fast-forward or a standard merge commit, the tree that lands on
`main` is the tree CI already tested.

Running the same 74-minute suite again after merge therefore proves nothing new.
In the baseline sample it accounted for roughly half the total spend: every
completed change paid for the suite twice.

The exception that makes this unsafe is a merge whose result CI never saw:

- a direct push to `main`;
- a merge of a PR whose branch was behind and was merged without re-testing;
- an administrative override.

Branch protection is what rules those out.

## Required settings

**Settings → Branches → Add branch ruleset** (or classic branch protection) for
`main`:

- [ ] **Require a pull request before merging.** This is the setting that makes
      the whole scheme sound. Without it, a direct push to `main` reaches
      production having been tested by nothing.
- [ ] **Require status checks to pass before merging**, and select exactly one
      check:
      ```
      CI summary
      ```
      Select **only** this one. The other jobs are conditional, and GitHub
      leaves a required check Pending forever when the job it names is skipped.
      `CI summary` always runs and fails if any lane the plan required did not
      succeed or did not run.
- [ ] **Require branches to be up to date before merging.** Without this, a PR
      tested against a stale base can merge into a `main` that has since moved,
      and the tested tree is not the merged tree.
- [ ] **Do not allow bypassing the above settings** (or restrict bypass to
      nobody). An admin override reintroduces exactly the untested-merge case.
- [ ] Optionally **Require linear history**, which keeps "the tested tree is the
      merged tree" trivially true.

## Until protection is on

`.github/workflows/ci.yml` keeps a safe fallback. The push-to-`main` run
currently executes the `plan`, `fast` and `affected` lanes — a real check on the
merged tree, at a fraction of the cost — rather than nothing.

If you decide **not** to protect `main`, restore the full post-merge suite by
setting `POST_MERGE_FULL=true` in the `plan` job's *Decide which lanes run*
step. That returns the duplicate cost, deliberately, and is the correct trade if
direct pushes to `main` remain possible.

## Verifying it worked

After enabling protection:

1. Open a trivial PR. Confirm `CI summary` is listed as required and that the
   merge button is blocked until it passes.
2. Confirm a direct `git push origin main` is rejected.
3. Confirm that a docs-only PR still merges — the summary must pass when every
   heavy lane was correctly skipped. If it goes Pending instead, the wrong check
   was marked required.
