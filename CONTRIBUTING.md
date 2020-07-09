# Contributing to the Mendix Buildpack

This document contains guidelines for contributing to the Mendix Buildpack (issues, PRs). Use in conjunction with [`DEVELOPING.md`](DEVELOPING.md) and [`LICENSE`](LICENSE).

We welcome your contributions! Please reach out to a maintainer if you need help or if you have any questions after reading this document.

## General Rules and Guidelines

The following rules and guidelines apply when contributing to the buildpack:

* For general Mendix support, please reach out to our regular channels instead of opening an issue specific to this buildpack.
* We require that you accept the license.
* If you're not a maintainer, use your own fork to develop and submit your PR on.
* New releases are always tagged `vX.X.X` . We make liberal use of semantic versioning.
* Our code complies to PEP8, is formatted in [`black`]((https://github.com/psf/black)) and linted in `pylint` .

## Issues

We have no formal issue template. If you submit an issue, please make sure that it contains all context we need to get started on it. Think logs, reproduction scenarios, etc. Any issue which is not complete will not be picked up, and please respect that we may ask you for any information we need to get started on an issue if it is not complete.

## PRs

The following guidelines must be respected to get your PR merged to `master` :

* Rebase your git history in such a way that each commit makes one consistent change. Don't include separate "fixup" commits later on.
* Submit your PR with all the information we need to review it. The same applies to PRs as it does to issues.
* The code must pass linting and all integration tests (in Travis). Code which does not pass will not be considered / reviewed. We have to be this strict since all deployments to the Mendix public cloud use the `master` branch.
* Always bump the version number in `.version` to an appropriate value.
* There is a minimum of one reviewer per PR.
* After a PR is merged, a release must be created with the appropriate version.
