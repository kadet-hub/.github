# Review gate

Status: Draft
Code: `.github/workflows/review-gate.yml`, `.github/review-gate/`, `.github/workflows/test.yml`, `README.md`
Verified against: main @ face044; reviews and status comments of `neat-bot` on kadet-hub pull requests, 2026-11-05

Related: kadet-hub/registry
[gate.md](https://github.com/kadet-hub/registry/blob/main/docs/specs/gate.md)
REV-4 (`neat-bot`'s review) and REV-5 (Renovate's merges).

## Problem

Most changes in kadet-hub are written by coding agents and reviewed by
`neat-bot`, an automated AI reviewer. A ruleset can require approvals only
from users with write access. `neat-bot` has read access, so no ruleset can
make its approval a merge condition, and the maintainer, who could
approve, is often away.

The review gate is a check that fails until `neat-bot` approved the pull
request's head commit and no maintainer has an open change request. A
repository's ruleset then requires the check. It started in
kadet-hub/registry#558 as a composite action of the registry and moved
here, so that every kadet-hub repository calls the same copy.

## Decisions

- DEC-1: The gate is a reusable workflow in this repository. A repository
  calls it from its own workflow, pinned by commit SHA.

  A public repository cannot call a workflow from a private one, and this
  repository is public. The pin keeps the code that judges a pull request
  out of that pull request: the decision script comes from this repository
  at the pinned commit, not from the commit under review.

- DEC-2: Only an approval of the head commit counts. `neat-bot`'s status
  comment does not.

  `neat-bot` keeps one status comment per pull request and rewrites it on
  every run. A result such as "2 finding(s), none judged useful" or "1
  finding(s), none above medium" comes with an approval of the head commit
  when `neat-bot` adds ", approved". Without that suffix the run posts no
  review (kadet-hub/registry#565). "no file was selected for review"
  means it reviewed no file. The six such pull requests checked changed
  only Markdown files.

  The comment names no commit, and a run that started before a push can
  write its result after it. In kadet-hub/examples#107 a commit pushed at
  about 08:21 UTC was followed at 08:21:14 by "2 finding(s), none judged
  useful" from the run that had started at 08:16:30 on the previous head.
  The new head never got a result of its own. A check that took a result
  written after the push as a review of the new head would have passed it
  unreviewed.

  Without an approval the gate stays red. The author requests a new
  review, or the maintainer merges through his admin bypass after a look
  of his own.

## Decision rule

The gate reads the pull request's reviews through the API. For each
reviewer it looks at the latest review, comment reviews included, so an
approval followed by a comment review with a new finding fails again. An
approval counts only with `commit_id` equal to the head commit of the
event that started the run.

A change request is open while its author's latest approval, change
request or dismissal is a change request. A later comment does not close
it, as on GitHub. Write access is `admin` or `write` in the collaborator
permission API, which maps maintain to write, and is looked up only for
users with an open change request.

Renovate merges its own pull request only once every check passed (REV-5),
and the gate cannot tell which of its pull requests Renovate will merge
itself, so all of them pass.

- RG-1: The `review-gate` job MUST fail until the latest review of every
  login in the `reviewers` input approves the pull request's head commit
  and no user with write access has an open change request. A pull request
  opened by `renovate[bot]` MUST pass.

  `reviewers` defaults to `neat-bot` and takes logins separated by spaces,
  so further AI reviewers can be added once they are named as such. Each
  of them must approve.

  - Test: `.github/review-gate/test_review_gate.py` against
    `fixtures.json`: approval of the head passes; a comment review with
    findings, an approval followed by a comment review, an approval of an
    older commit, a maintainer's change request (also after his later
    comment), no review, a maintainer pull request without a review, and
    a second reviewer who has not approved fail; a dismissed change
    request, a change request followed by the same reviewer's approval, a
    change request without write access, two reviewers who both approved
    and a Renovate pull request pass. `Decide` also checks that write
    access is looked up only for change requesters and that a review by a
    deleted account is ignored.
  - Since: this change

## Fork pull requests

`pull_request` and `pull_request_review` both give a pull request from a
fork a read-only token and no secrets. The job reads reviews and
permissions through the API and checks out nothing. It downloads
`review_gate.py` through the contents API from `job.workflow_repository`
at `job.workflow_sha`, which name this repository and the commit the
caller pinned.

- RG-2: The job MUST hold `pull-requests: read` as its only permission,
  MUST NOT check out or run code of the pull request, and MUST run the
  decision script of the commit the caller pinned.

  - Test: `.github/review-gate/test_review_gate.py`
    `Workflow.test_read_only_and_pinned`
  - Since: this change

## Calling the gate

A repository adds a workflow with the triggers below and a job that calls
the gate. README.md has the snippet. With a caller job named
`review-gate`, the check is named `review-gate / review-gate`, and that is
the name a ruleset requires.

A push starts a run that fails until `neat-bot` approves the new head, and
the approval starts the run that passes. Each run judges the head commit of
its event, which is the commit its check attaches to. A newer run of the
same pull request cancels an older one, so a stale result cannot land last.

- RG-3: A repository MUST call the gate pinned by full commit SHA, from a
  workflow that runs on `pull_request` (opened, synchronize, reopened) and
  `pull_request_review` (submitted, dismissed), with `pull-requests: read`
  as its permissions. This repository calls its own gate the same way.

  A local call (`./.github/workflows/review-gate.yml`) would run the
  decision script of the commit under review.

  - Test: manual: the caller workflow of each repository
  - Since: not implemented

## How changes are reviewed

- RG-4: README.md MUST carry a "How changes are reviewed" text that
  repositories copy. It MUST say that reviews are automated, name each AI
  reviewer with its model, say that a pull request merges only after their
  approval of the head commit, and say that the maintainer can block a pull
  request with a change request.

  - Test: none (documentation)
  - Since: this change

## Open questions

- OQ-1: Which Qwen model and version does `neat-bot` run? README.md names
  the model family only, the version is tbd.

## Implementation inventory

| Path | Requirement |
|---|---|
| `.github/workflows/review-gate.yml`: the reusable workflow, input `reviewers` | RG-1, RG-2 |
| `.github/review-gate/review_gate.py`, `fixtures.json`, `test_review_gate.py` | RG-1, RG-2 |
| `.github/workflows/test.yml`: runs the tests on pull requests that change the gate | RG-1, RG-2 |
| `README.md`: caller snippet and the "How changes are reviewed" text | RG-3, RG-4 |
