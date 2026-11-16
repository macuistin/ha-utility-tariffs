# Docs, writing and workflow

## Writing

- UK English everywhere: code comments, docs, strings, commits (behaviour, colour, licence).
- Short sentences, action verbs, concrete names (files, fields, entities). A paragraph over three
  sentences is usually overwritten.
- No em dash to bolt on an afterthought. Use a comma or a full stop, or reword.
- A comment says why, never what the next line does. Delete commented-out code.

## Docs are generic

`README.md`, `docs/` and every user-facing string are written for any user with any supplier and
tariff. They never mention the maintainer, one household's bill, personal device or people names,
serial numbers, URLs or avatars. Describe a setting by its meaning and unit, with a labelled round
number example.

## Commits and pull requests

- Conventional Commits for commit messages and PR titles: `feat(sensor): ...`, `fix(config): ...`.
- No `Co-Authored-By` line and no "Generated with" line in commits or PR bodies. If a tool adds
  one, edit it out.
- PR body: `.github/PULL_REQUEST_TEMPLATE.md`. List what was not verified under Testing.
- Related PRs are stacked: each is based on the branch below it. Merge commits, not squash.
- Never rebase, amend or force-push a branch that has an open PR. Address review feedback with
  new commits.
- When a lower PR merges, retarget the next one to `main` and merge `main` into it.
- Nothing merges unless CI is green on the exact head commit.
