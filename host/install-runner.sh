#!/usr/bin/env bash
# Chapter 3: install a GitHub self-hosted runner for ONE repository and run it
# as a system service. Requires: gh auth login (done once), Docker group membership.
# Usage: ./install-runner.sh OWNER/REPO
set -euo pipefail

repo="${1:?usage: $0 OWNER/REPO}"
label="devsecops"
dir="$HOME/actions-runner"

version="$(gh api repos/actions/runner/releases/latest --jq .tag_name)"
version="${version#v}"
echo "Installing runner ${version} for ${repo} with label '${label}'"

mkdir -p "$dir" && cd "$dir"
curl -fsSL -o runner.tar.gz \
  "https://github.com/actions/runner/releases/download/v${version}/actions-runner-linux-x64-${version}.tar.gz"
tar xzf runner.tar.gz && rm runner.tar.gz

# A registration token is valid for one hour and only registers runners.
token="$(gh api -X POST "repos/${repo}/actions/runners/registration-token" --jq .token)"
./config.sh --unattended --url "https://github.com/${repo}" --token "$token" \
  --name "$(hostname)" --labels "$label" --replace
unset token

sudo ./svc.sh install "$USER"
sudo ./svc.sh start
sudo ./svc.sh status | head -n 5
echo "Check GitHub: ${repo} -> Settings -> Actions -> Runners shows the runner as Idle."
