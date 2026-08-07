#!/usr/bin/env bash
# Install Docker Engine inside the WSL2 Ubuntu distribution.
#
# NOT Docker Desktop. Docker Desktop carries a commercial licensing requirement
# for government entities and larger organisations; Docker Engine is Apache-2.0
# and has no such requirement. This script installs Engine, the CLI, containerd,
# Buildx and the Compose plugin from Docker's official Ubuntu apt repository.
#
# It is a script rather than something the agent ran because every step needs
# sudo, and sudo on this machine requires a password that cannot be supplied
# non-interactively.
#
# Verified against this machine before it was written:
#   distribution  Ubuntu 24.04.2 LTS (noble)      - a currently supported release
#   kernel        6.6.87.2-microsoft-standard-WSL2
#   init          systemd 255                      - so the daemon can be a service
#   cpus          20
#   free disk     948G on /
#
# Run it from inside WSL:
#
#     wsl
#     bash /mnt/c/Users/<you>/Repos/NLTF-revenue-ci-optimisation/ci/install_docker_engine_wsl.sh
#
# It changes nothing on the Windows side: no Windows services, no Windows
# environment variables, no Windows features.

set -euo pipefail

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m!! %s\033[0m\n' "$*"; }

# --- 0. Preconditions --------------------------------------------------------
say "Checking preconditions"

if ! grep -qi microsoft /proc/version; then
  echo "This does not look like WSL. Run it inside the WSL Ubuntu distribution." >&2
  exit 1
fi

. /etc/os-release
if [ "${ID:-}" != "ubuntu" ]; then
  echo "Expected Ubuntu, found ${ID:-unknown}. Stopping rather than guessing." >&2
  exit 1
fi
case "${VERSION_CODENAME:-}" in
  noble|jammy|focal) ;;
  *)
    echo "Ubuntu ${VERSION_CODENAME:-?} is not a release Docker publishes packages for." >&2
    echo "Stopping. Report this rather than forcing the install." >&2
    exit 1
    ;;
esac
echo "Ubuntu ${VERSION_ID} (${VERSION_CODENAME}) - supported."

if ! sudo -v; then
  echo "sudo is required and unavailable." >&2
  exit 1
fi

# systemd is what lets the daemon run as a managed service across shells. WSL
# only provides it when /etc/wsl.conf opts in.
if ! pidof systemd >/dev/null 2>&1; then
  warn "systemd is not running as PID 1 in this distribution."
  warn "Add the following to /etc/wsl.conf, then run 'wsl --shutdown' from Windows"
  warn "and reopen WSL:"
  warn ""
  warn "    [boot]"
  warn "    systemd=true"
  warn ""
  warn "Without it the daemon must be started by hand ('sudo dockerd &') each time."
  read -r -p "Continue anyway? [y/N] " reply
  [ "$reply" = "y" ] || exit 1
fi

# --- 1. Remove distro packages that conflict --------------------------------
say "Removing any conflicting distribution packages"
for pkg in docker.io docker-doc docker-compose docker-compose-v2 podman-docker containerd runc; do
  sudo apt-get remove -y "$pkg" >/dev/null 2>&1 || true
done

# --- 2. Docker's apt repository ---------------------------------------------
say "Adding Docker's official apt repository"
sudo apt-get update
sudo apt-get install -y ca-certificates curl

sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
     -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update

# --- 3. Install --------------------------------------------------------------
say "Installing Docker Engine, CLI, containerd, Buildx and Compose"
sudo apt-get install -y \
  docker-ce \
  docker-ce-cli \
  containerd.io \
  docker-buildx-plugin \
  docker-compose-plugin

# --- 4. Start ----------------------------------------------------------------
say "Starting the daemon"
if pidof systemd >/dev/null 2>&1; then
  sudo systemctl enable --now docker
  sudo systemctl --no-pager status docker | head -5 || true
else
  sudo service docker start || true
fi

# --- 5. Verify ---------------------------------------------------------------
say "Verifying"
sudo docker version
sudo docker compose version
sudo docker buildx version
sudo docker run --rm hello-world

# --- 6. The docker group is deliberately NOT configured ----------------------
say "Done"
cat <<'EOF'

Docker Engine is installed and working under sudo.

This script deliberately did NOT run:

    sudo usermod -aG docker $USER

Membership of the docker group is equivalent to passwordless root on this
distribution: any member can start a container that mounts the host filesystem.
That may well be an acceptable trade for a personal dev box, but it is a real
privilege decision and it should be made deliberately, not as a side effect of
an install script.

If you want it:

    sudo usermod -aG docker $USER
    newgrp docker          # or close and reopen WSL

Otherwise, run the CI wrappers with sudo:

    sudo scripts/ci_local.sh --tier fast

Next: clone a working copy into the Linux filesystem, because bind-mounting
from /mnt/c is significantly slower than ext4 under WSL2:

    mkdir -p ~/nltf-ci
    cd ~/nltf-ci
    git clone /mnt/c/Users/<you>/Repos/NLTF-revenue-ML-model-dashboard repo
    cd repo
    git checkout performance/ci-runtime-optimisation
    scripts/ci_local.sh --tier fast

The Windows checkout is never touched by any of this.
EOF
