# kadet-hub/.github

kadet-hub's organization profile (`profile/`), the default security policy
and issue forms, and the review gate the other repositories call.

## Review gate

`.github/workflows/review-gate.yml` is a check that fails until the AI
reviewers approved the pull request's head commit and no maintainer has an
open change request. Its rules are in
[docs/specs/review-gate.md](docs/specs/review-gate.md).

A repository calls it from its own `.github/workflows/review-gate.yml`:

```yaml
name: review-gate

on:
  pull_request:
    types: [opened, synchronize, reopened]
  pull_request_review:
    types: [submitted, dismissed]

permissions:
  pull-requests: read

jobs:
  review-gate:
    uses: kadet-hub/.github/.github/workflows/review-gate.yml@<sha> # main
```

`<sha>` is the full SHA of a commit on this repository's `main`. The input
`reviewers` takes the reviewer logins separated by spaces and defaults to
`neat-bot`; each of them must approve. The check is named
`review-gate / review-gate`, and a ruleset requires it under that name with
GitHub Actions as its source.

The check runs on every push and on every submitted or dismissed review.
A result in `neat-bot`'s status comment without an approval does not pass
it and does not run it again, so request `neat-bot`'s review again until it
approves.

## How changes are reviewed

A text for a repository's README. List every reviewer the repository's
`reviewers` input names.

```markdown
## How changes are reviewed

Reviews here are automated. `neat-bot` is an AI reviewer, not a person. A
Qwen model (version tbd) finds the issues, and Claude Sonnet decides which
of them `neat-bot` posts. A pull request merges only after `neat-bot`
approved its current head commit, and the `review-gate` check fails until
it has. The author fixes each finding or answers it in its thread.

No person reviews the maintainer's own pull requests or those coding agents
open for the maintainer. The maintainer can block any pull request with a
change request. It stays blocked until the maintainer approves it or
dismisses the request. Renovate merges most dependency updates without
`neat-bot`, once every check passed.
```
