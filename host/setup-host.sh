#!/usr/bin/env bash
# Chapter 2: prepare a fresh Ubuntu 24.04 VM as the lab host.
# Installs Docker Engine + Compose from Docker's official apt repository,
# plus git, python3, curl and the GitHub CLI. Run as the normal VM user.
set -euo pipefail

# shellcheck source=/dev/null
. /etc/os-release
if [[ "${ID}" != "ubuntu" ]]; then
  echo "This script expects Ubuntu (found ${ID})." >&2
  exit 1
fi

sudo apt-get update
sudo apt-get install -y ca-certificates curl git python3 gh

if ! command -v docker >/dev/null 2>&1; then
  sudo install -m 0755 -d /etc/apt/keyrings
  sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  sudo chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
    | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
  sudo apt-get update
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi

sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"

echo
echo "Done. Log out and back in (exit, then ssh again) so the docker group applies."
echo "Then check:  docker run --rm hello-world"
