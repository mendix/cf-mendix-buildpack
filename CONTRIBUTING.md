# Contributing to the Mendix Buildpack

This document contains guidelines for contributing to the Mendix Buildpack (issues, PRs). Use in conjunction with [ `DEVELOPING.md` ](DEVELOPING.md) and [ `LICENSE` ](LICENSE).

We welcome your contributions! Please reach out to a maintainer if you need help or if you have any questions after reading this document.

## General Rules and Guidelines

The following rules and guidelines apply when contributing to the buildpack:

* For general Mendix support, please reach out to our regular channels instead of opening an issue specific to this buildpack.
* We require that you accept the [`LICENSE`](LICENSE).
* We follow a `develop` to `master` flow, where `master` is always the latest tested / released / working branch. Features are in `DEP-*` branches and may only be merged to `develop`. Releases (`release-*`) and fixes (also `DEP-*`) have separate branches and may be merged into `master`. For inspiration, check [this article](https://nvie.com/posts/a-successful-git-branching-model/).
* New releases are always tagged `vX.X.X` . We make liberal use of semantic versioning.
* Our code complies to PEP8, is formatted in [`black`]((https://github.com/psf/black)) and linted in `pylint`.

## Issues

We have no formal issue template. If you submit an issue, please make sure that it contains all context we need to get started on it. Think logs, reproduction scenarios, etc. Any issue which is not complete will not be picked up, and please respect that we may ask you for any information we need to get started on an issue if it is not complete.

## PRs

The following guidelines apply to pull requests:

* Base your PR on the **right branch**. Anything other than releases and hotfixes must be based on the `develop` branch and must be targeted to the `develop` branch.
* Submit your PR with **all the information** we need to review it. This includes a sensical title and accurate description.
* The code must **pass linting and all (integration) tests**. Code which does not pass will not be considered / reviewed.
* Please ensure that you have a **condensed commit history**; thousands of small commits are hard to squash.
* There is a **minimum of one reviewer** per PR.

### Merge Procedure

0. Ensure that your branch is based on the latest `develop` version.
1. Ask at least one person to review the PR.
2. Merge to `develop` using the **"Squash and Merge"** strategy.

After a PR is merged to `develop` , be sure to:

* **Delete** your branch.

## Releases and Hotfixes

The following guidelines apply to releases and hotfixes:

* Release and hotfix are PRs, and therefore must follow the **PR guidelines**.
* Release and hotfix PRs contain a version bump in the form of a commit of `VERSION`.
* Release PRs only contain a version bump commit besides the changes from `develop`. Hotfix PRs may contain commits that are not in `develop`.
* Release and hotfix PR **titles** must be prefixed by the version, e.g. `vx.x.x: Release Title`.
* Base the release or hotfix PR on the `develop` (release) or `master` (hotfix) branch, and target the `master` branch.
* Please clean up any branch that has been merged into `develop` or `master`.

### Release Procedure

0. Ensure that your branch is based on the latest `develop` (release) or `master` (hotfix) version.
1. Add an **commit to the PR to bump the version number** in `VERSION` to an appropriate value.
2. Ask at least one person to review the PR. This review counts as a release approval; in the case of a release, this is a formality.
3. Merge to `master` using the **"Rebase and Merge"** strategy.

After a release or hotfix PR is merged to `master`, a draft release is created automatically. Be sure to:

* **"Undraft"** the release to release it.
* **Delete** your release or hotfix branch.
* **Rebase** `master` on `develop`, and **force push** it to ensure that the version bump commit is in `develop`.
