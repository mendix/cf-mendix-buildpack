# Contributing to the Mendix Buildpack

This document contains guidelines for contributing to the Mendix Buildpack (issues, PRs). Use in conjunction with [`DEVELOPING.md`](DEVELOPING.md) and [`LICENSE`](LICENSE).

We welcome your contributions! Please reach out to a maintainer if you need help or if you have any questions after reading this document.

## General Rules and Guidelines

The following rules and guidelines apply when contributing to the buildpack:

* For general Mendix support, please reach out to our regular channels instead of opening an issue specific to this buildpack.
* We require that you accept the [`LICENSE`](LICENSE).
* We follow a `develop` to `master` flow, where `master` is always the latest tested / released / working branch. Features are in separate branches and may only be merged to `develop`. Hotfixes also have separate branches and may be merged into `master`. For inspiration, check [this article](https://nvie.com/posts/a-successful-git-branching-model/).
* New releases are always tagged `vX.X.X` . We make use of semantic versioning, and version numbers are [generated automatically based on the commit history](#releases-and-hotfixes).
* Our code complies to PEP8, is formatted in [`ruff`](https://beta.ruff.rs/docs/) and linted in [`pylint`](https://pylint.readthedocs.io/en/latest/).

## Issues

We have no formal issue template. If you submit an issue, please make sure that it contains all context we need to get started on it. Think logs, reproduction scenarios, etc. Any issue which is not complete will not be picked up, and please respect that we may ask you for any information we need to get started on an issue if it is not complete.

## PRs

The following guidelines apply to pull requests:

* Base your PR on the **right branch**. Anything other than hotfixes must be based on the `develop` branch and must be targeted to the `develop` branch.
* Submit your PR with **all the information** we need to review it. This includes a sensical title and accurate description.
* The code must **pass linting and all (integration) tests**. Code which does not pass will not be considered / reviewed.
* Please ensure that you have a **condensed commit history**; thousands of small commits are hard to squash.
* There is a **minimum of one reviewer** per PR.

### Merge Procedure

1. Ensure that your branch is based on the latest `develop` version.
2. Ask at least one person to review the PR.
3. Merge to `develop` using the **"Squash and Merge"** strategy.

After a PR is merged to `develop` , be sure to:

* **Delete** your branch.

## Releases and Hotfixes

The following guidelines apply to releases and hotfixes:

* Release and hotfix are PRs, and therefore must follow the **PR guidelines**.
* Release and hotfix PRs [automatically generate a semantic version number](https://github.com/marketplace/actions/git-semantic-version) based on the commit history:
  * If a commit message title contains `(major)`, the major version number will be bumped. This takes precedence over any minor and patch version bumps.
  * If a commit message title contains `(minor)`, the minor version will be bumped. This takes precedence over any patch version bumps.
  * If a commit message title does not contain any of the above, the patch version will be bumped **once**
* Release PRs merge `develop` into `master`, and do not need a separate branch. Hotfix PRs may contain commits that are not in `develop`, and need a separate branch.
* Release and hotfix PR **titles** are automatically prefixed by the version, e.g. `vx.x.x: Release Title`.
* Base the release or hotfix PR on the `develop` (release) or `master` (hotfix) branch, and target the `master` branch.
* Please clean up any branch that has been merged into `develop` or `master`.

### Release Procedure

0. Ensure that you are merging `develop` to `master` (release), or that your branch is based on `master` (hotfix).
1. Ask at least one person to review the PR. This review counts as a release approval; in the case of a release, this is a formality.
2. Merge to `master` using the **"Merge Commit"** strategy.

After a release or hotfix PR is merged to `master`, a draft release is created automatically. Be sure to:

* **Edit** the draft release:
  * Press the magic [**"Automatically generate changelog"** button](https://docs.github.com/en/repositories/releasing-projects-on-github/automatically-generated-release-notes#creating-automatically-generated-release-notes-for-a-new-release) to include the changelog
  * Release the release, i.e. **"undraft"** it
* For a hotfix:
  * **Delete** your release or hotfix branch.
  * Ensure that the changes from `master` are [backmerged](#backmerge-hotfixes) into `develop`.

#### Backmerge Hotfixes

If you merge a change directly from a hotfix branch into `master`, it will not automatically also be included in `develop`. Since `develop` is a protected branch, pushing to this branch cannot be automated with Github Actions.

To get hotfix changes into `develop`, **backmerge** them:

```shell
git fetch origin develop
git fetch origin master
git checkout develop
git pull
git merge origin/master
git push
```

The above series of commands will fetch the remote origin branches, checkout the `develop` branch, merge `master` into `develop`, and push the result.
