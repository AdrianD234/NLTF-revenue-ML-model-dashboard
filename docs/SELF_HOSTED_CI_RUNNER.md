# Optional self-hosted CI runner

**Status: not installed. Nothing in this repository requires it.**

This document describes an option, not a decision. No runner has been
registered, and `.github/workflows/ci.yml` does not reference `self-hosted`
labels. Registering one is an owner action with real security consequences, so
it is described here and left for the owner to take deliberately.

Read the security section before deciding.

---

## What it would buy

The `full-assurance` job is the expensive lane: about 75 minutes on a
GitHub-hosted 2-CPU runner, and roughly $0.60 of hosted time each. The same
suite on this machine — 20 logical CPUs, 31 GB RAM — completes in a small
fraction of that.

A self-hosted runner would let that job run on the local machine, in the same
`ci/Dockerfile` image, while still appearing as a normal GitHub check on the
pull request. GitHub does not bill for self-hosted runner minutes.

So: the check stays visible and enforceable, the wall time drops, and the hosted
bill for that lane goes to zero.

## What it would cost

- A machine that must be online when a PR wants the check. An offline required
  runner leaves pull requests queued indefinitely — which is why the workflow
  must not require it until it demonstrably works (see *Rollout* below).
- Maintenance: runner updates, disk pressure from Docker layers, and the
  security posture below.

---

## Security rules

These are not optional. A self-hosted runner executes whatever code a workflow
tells it to, on a persistent machine that keeps state between jobs.

- **Private repository only.** This repository is private, which is the
  precondition. Never attach this runner to a public repository.
- **No untrusted fork pull requests.** GitHub's own guidance is explicit: a fork
  PR can modify the workflow it runs under. On a public repo that is remote code
  execution on your machine. Keep `pull_request_target` out of any workflow that
  targets this runner.
- **Trusted branches and workflows only.** Restrict the runner to a runner group
  scoped to this repository, and to the workflows that genuinely need it.
- **A dedicated user or VM.** Do not run the agent as your own account. It
  should not be able to read your SSH keys, browser profiles, cloud credentials,
  password manager, or the rest of your home directory.
- **No broad machine credentials.** No cloud CLI logins, no long-lived tokens in
  the runner's environment.
- **No secrets baked into the Docker image.** The image is a build artefact and
  may be cached, exported or shared.
- **Clean the work directory between jobs.** Prefer an ephemeral (`--ephemeral`)
  runner that deregisters after each job, so a compromised job cannot persist.
- **Never register automatically.** Not from a script, not from an agent, not as
  a side effect of another task.

If a dedicated VM is not practical, do not install this. Hosted runners are
cheaper than a compromised workstation.

---

## Installation (owner action)

1. Create a dedicated OS user, or better, a VM with Docker installed.
2. In GitHub: **Settings → Actions → Runners → New self-hosted runner**, choose
   Linux x64, and follow the generated commands. Do not paste the registration
   token anywhere else.
3. Apply these labels:
   ```
   self-hosted
   nltf-ci
   linux
   x64
   ```
4. Prefer ephemeral operation:
   ```bash
   ./config.sh --url https://github.com/AdrianD234/NLTF-revenue-ML-model-dashboard \
               --token <REGISTRATION_TOKEN> \
               --labels nltf-ci,linux,x64 \
               --ephemeral
   ```
5. Verify Docker works as the runner user:
   ```bash
   docker run --rm hello-world
   ```

## Uninstallation

```bash
./config.sh remove --token <REMOVAL_TOKEN>
```

Then delete the runner directory, remove the OS user or VM, and prune Docker:

```bash
docker system prune -a
```

Remove the runner from **Settings → Actions → Runners** if it does not
deregister itself.

---

## Rollout — do not skip this order

The workflow must not require this runner until it exists and has proven itself.
A required check pointing at an offline runner blocks every pull request.

1. Register the runner. Change nothing in the workflow.
2. Add a **non-required** experimental job targeting
   `runs-on: [self-hosted, nltf-ci, linux, x64]` that runs the `full` tier via
   the container. Let it run alongside the hosted job for several real changes.
3. Compare, for the same commit: the selected test inventory, the pass/fail set,
   pack statuses, and the replay fingerprint. They must match. If a governed
   value differs between the runner and hosted CI, stop and investigate — that
   is a genuine cross-environment finding, not a runner configuration detail.
4. Only after that, move the `full-assurance` job to the runner, and keep a
   `workflow_dispatch` path that forces it back onto a hosted runner.
5. Keep the hosted fallback wired up permanently. When the runner is offline the
   fallback must take over, not queue.

## Offline behaviour

A job whose `runs-on` labels match no online runner **queues**; it does not fail
and does not time out quickly. If the runner is the only thing that can satisfy
a required check, pull requests stall silently.

Mitigations, in order of preference:

- keep `full-assurance` on hosted runners and use the self-hosted one only for
  optional, scheduled or dispatch-triggered deep assurance;
- give the job a short `timeout-minutes` so a stalled queue surfaces quickly;
- keep the runner's health visible in **Settings → Actions → Runners** before
  relying on it for a merge.
