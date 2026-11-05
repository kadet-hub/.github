# Agent tools

Tools for the maintainer's coding-agent sessions. The rules they implement
are AGT-4 and AGT-5 in kadet-hub/registry
[`docs/specs/agents.md`](https://github.com/kadet-hub/registry/blob/main/docs/specs/agents.md).
[sessions.md](sessions.md) sets up the separate OS user or the container a
session runs in.

## mint-token

`mint-token` prints an installation token of the agent app
(`kadet-hub-agent`, name tbd) for the repositories you name. GitHub limits
the token to those repositories and lets it expire after one hour. A session
gets it as `GH_TOKEN`, which `gh` and, through `gh auth setup-git`, `git`
both use.

It needs bash, openssl, curl, jq and the 1Password CLI `op` with the
desktop app integration, which asks for approval before each read. On
Fedora, `sudo dnf install openssl curl jq`; `op` comes from 1Password's own
package repository.

Two variables tell it which app and key to use:

| Variable | Value |
|---|---|
| `AGENT_APP_ID` | Client ID from the app's settings page, or the numeric app ID (tbd) |
| `AGENT_KEY_REF` | `op://<vault>/<item>/<field>` of the private key in 1Password (tbd) |

```sh
token=$(tools/agent/mint-token registry recipes)
```

[sessions.md](sessions.md) shows how `$token` becomes the session's
`GH_TOKEN`.

The script reads the key with `op read` and pipes it straight into
`openssl`, which signs a JWT valid for ten minutes. It never stores the key
in a file, a shell variable or a command-line argument. It looks up the
app's installation on kadet-hub, asks for a token limited to the named
repositories, and prints only that token. `curl` gets the JWT on standard
input, because other local users can read a process's command line.

On a refusal it prints GitHub's status and message to stderr, nothing to
stdout, and exits non-zero, so `token=$(...) && ...` stops there. A
repository the app is not installed on gives HTTP 422.

Run it from a clone of `main`. The script handles the app key, and
CODEOWNERS makes every change under `tools/` wait for the maintainer once
this repository's ruleset requires code owner review.

## Test

```sh
python3 -m unittest discover -s tools/agent -v
```

The test generates a throwaway RSA key, puts a fake `op` and a `curl`
wrapper that records its arguments on `PATH`, and points the script at a
local fake API through `GITHUB_API_URL`. It checks that only the token
reaches stdout, that the JWT verifies against the throwaway key with the
expected claims, that the request names the repositories, that neither key
nor JWT appears in any output or on `curl`'s command line, that the working
and temporary directories stay empty, that a refusal is reported, and that
a call without repositories is rejected. The `tools` workflow runs it on
pull requests that change `tools/`.
