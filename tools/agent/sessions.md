# Agent sessions on Fedora

An agent session is a Claude Code session whose only GitHub credential is a
token of the agent app in `GH_TOKEN` (AGT-5 in kadet-hub/registry
[`docs/specs/agents.md`](https://github.com/kadet-hub/registry/blob/main/docs/specs/agents.md)).
It runs either as a separate OS user or in a rootless podman container.
Both keep the session away from the maintainer's `$HOME`, the keyring that
holds the `gh` logins of the maintainer and neat-bot, the 1Password CLI,
`~/.vault-token`, and the SSH and GPG keys. Pick one per machine. The
identity setup and the checks at the end are the same for both.

| What the session must not reach | Separate OS user | Rootless container |
|---|---|---|
| `$HOME` with `~/.config/gh`, `~/.vault-token`, `~/.ssh`, `~/.gnupg` | Fedora creates home directories with mode 0700 (`HOME_MODE` in `/etc/login.defs`) | Not mounted |
| Keyring, 1Password app integration, ssh-agent and gpg-agent | Their sockets sit in directories only the maintainer can open, under `$HOME`, `/run/user/<uid>` or `/tmp` | Not mounted |
| Environment such as `VAULT_ADDR`, `VAULT_TOKEN`, `SSH_AUTH_SOCK` | `run0` starts from a clean environment and passes only `--setenv` | `podman run` passes only `--env` |
| Files the maintainer leaves readable in `/tmp`, command lines of the maintainer's processes | `PrivateTmp=yes` and `ProtectProc=invisible` on the session | The container's own `/tmp` and process namespace |

The token comes from [`mint-token`](README.md), run as the maintainer. It
covers the repositories named and expires after one hour. The commands
below assume a reviewed copy of it on the maintainer's `PATH`.

## Separate OS user

Once, as the maintainer:

```sh
sudo useradd --comment 'kadet-hub agent sessions' agent
stat -c '%a' ~          # 700: no other user can read your home
sudo dnf install git gh jq
```

`useradd` does not put the agent user into `wheel`, so it cannot use
`sudo`, and `run0` would ask it for an administrator's password. Claude
Code has to be installed system-wide, since an install from the
native installer lives in the maintainer's home. Anthropic's dnf
repository does that:

```sh
sudo tee /etc/yum.repos.d/claude-code.repo <<'EOF'
[claude-code]
name=Claude Code
baseurl=https://downloads.claude.ai/claude-code/rpm/stable
enabled=1
gpgcheck=1
gpgkey=https://downloads.claude.ai/keys/claude-code.asc
EOF
sudo dnf install claude-code
```

dnf asks to import the repository key. Accept it only if the fingerprint
is `31DD DE24 DDFA B679 F42D 7BD2 BAA9 29FF 1A7E CACE`, the one Claude
Code's setup page lists.

Each session:

```sh
token=$(mint-token registry recipes) &&
  GH_TOKEN=$token run0 --user=agent --setenv=GH_TOKEN \
    --property=PrivateTmp=yes --property=ProtectProc=invisible -i
```

`run0` needs systemd 258 or newer for `-i` (`systemctl --version`) and asks
for your password through polkit. It hands `GH_TOKEN` to the service
manager as the environment of the session's transient unit, and
`systemctl show` displays that environment to every local user while the
session runs. On a workstation whose only other account is the agent
user, nobody learns the token who does not hold it already.

The session starts in the agent's home. Clone the repositories there
(`gh repo clone kadet-hub/registry`) and run `claude`. The first start asks
for a Claude login, which then stays in the agent's home. Copy the
instructions and skills the agents need into the agent's `~/.claude/`, and
leave out MCP server configurations that carry tokens.

## Rootless podman container

Once, as the maintainer, in an empty directory outside every repository,
write `claude-code.repo` with the repository block from the section above
and this `Containerfile`:

```dockerfile
FROM registry.fedoraproject.org/fedora:44
COPY claude-code.repo /etc/yum.repos.d/
RUN dnf -y install git gh jq python3 claude-code && dnf clean all \
 && useradd --create-home agent
USER agent
WORKDIR /home/agent
```

```sh
podman build -t localhost/agent-session .
podman volume create agent-home
```

Use the Fedora release of the host. `dnf -y` imports the Claude Code
repository key without asking, so compare the fingerprint in the build
output with the one above. Rebuild to pick up updates.

Inside the container the session runs as `agent`, which rootless podman
maps to a subordinate UID of the maintainer's, not to the maintainer's UID.
The volume keeps the agent's home, its Claude login and the clones between
sessions; nothing else of the host is mounted.

Each session:

```sh
token=$(mint-token registry recipes) &&
  GH_TOKEN=$token podman run --rm -it --env GH_TOKEN \
    --volume agent-home:/home/agent localhost/agent-session
```

`--env GH_TOKEN` without a value takes it from podman's own environment, so
the token does not appear on a command line. Then clone and run `claude` as
above.

## Identity, once per agent home

Inside a session, with `<bot user id>` from
`gh api 'users/kadet-hub-agent[bot]' --jq .id`:

```sh
git config --global user.name 'kadet-hub-agent[bot]'
git config --global user.email '<bot user id>+kadet-hub-agent[bot]@users.noreply.github.com'
gh auth setup-git
```

`gh auth setup-git` makes `gh auth git-credential` the credential helper for
github.com. It answers `git push` with `x-access-token` and the value of
`GH_TOKEN`. The agent's git configuration has no signing key and no
`commit.gpgsign`, so its commits are unsigned (AGT-6). Agent commits carry
no `Signed-off-by` (AGT-8), so `git commit -s` is not used here.

## Checks

Run these in every new agent home or image, and after changing the setup.
Each line names what it must show.

```sh
env -u GH_TOKEN gh auth status     # "You are not logged into any GitHub hosts"
gh api user                        # HTTP 403: an app token has no user
gh api installation/repositories --jq '.repositories[].full_name'   # only the repositories minted for
git config --get commit.gpgsign    # nothing
ssh-add -l                         # no connection to an agent
gpg --list-secret-keys             # nothing
env | grep -c '^VAULT_'            # 0
ls "$(getent passwd <maintainer> | cut -d: -f6)"   # fails: permission denied, or no such user in the container
ps -e                              # only this session's processes
```

## After an hour

The token expires one hour after it was minted, and `gh` and `git push`
then fail with HTTP 401. Leave the session, mint a new token, start the
session again, and resume the conversation with `claude --continue` in the
same directory. Whether a credential helper should mint on demand instead
is open (OQ-56).
