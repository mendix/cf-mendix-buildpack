# Mendix Buildpack Development
This document describes best practices of developing the Mendix Buildpack. Use in conjunction with [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Buildpack Structure
The buildpack features the following directories:
* `bin`: Cloud Foundry buildpack lifecycle scripts, utility scripts and binaries live here
* `buildpack`: All Python code lives here, this is the home of the main buildpack module. Entry points are `compile.py` and `start.py`
* `docs`: Extra documentation in Markdown format lives here
* `etc`: Configuration templates for e.g. nginx and M2EE live here
* `lib`: A forked version of M2EE Tools suited for the cloud lives here, used for working with the Mendix Runtime
* `tests`: All test code lives here
* `vendor`: All vendorized dependencies live here

## Prerequisites
The buildpack is a Python project, and you must have some experience in Python, bash and the `make` system to develop.

For developing the buildpack, `pyenv` must be set up, and the dependencies for testing and linting must be installed. Additionally, you must have a Cloud Foundry cluster available for testing with all the required service brokers installed, and configure your environment to point to that cluster.

### Installing `pyenv`
[pyenv](https://github.com/pyenv/pyenv) in combination with [pyenv-virtualenv](https://github.com/pyenv/pyenv-virtualenv) can be used to create a local sandbox to develop in. Note that you'll have to create an environment with the latest version of Python 3.6 - the default in the Cloud Foundry root filesystem we use to deploy applications on.

Beware that an older file system is also supported which includes Python 3.4, so please take that into account while introducing additional dependencies or new dependency version.

### Installing testing and linting requirements
The buildpack makes use of the `make` system. For dependency management, `pip-compile` is used under the hood.

If you're using a Mac, be sure to use Brew to install `coreutils` and `findutils`.

A few `make` targets to use are:

* `vendor`: downloads the Python runtime dependencies as wheels into `vendor/wheels`
* `install_build_requirements`: installs the build / runtime requirements
* `install_test_requirements`: installs the test requirements
* `install_lint_requirements`: installs the linting / formatting requirements

**Never change the `requirements*.txt` files directly!** Use `requirements*.in` to that.

### Setting up your environment
For integration tests, you need to use a fully-featured Cloud Foundry cluster containing the Mendix S3, RDS and backup (Schnapps) service brokers. Once you have that in place, you'll need to set up the following environment variables:

```
export BUILDPACK="<your custom buildpack name>"
export TEST_PREFIX="<prefix identifying your test run app for others>
export CF_ENDPOINT="<your testing cluster API endpoint>"
export CF_USER="<your username>"
export CF_PASSWORD="<your password>"
export CF_ORG="<test org>"
export CF_SPACE="<test space>"
export CF_DOMAIN="<your test domain>"
export MX_PASSWORD="<sample password for Mendix apps deployed during testing>"
```

## Building
To ensure that your CF cluster has the buildpack you're developing available, use the following `make` targets:

* `clean`: removes all the nasties, including leftover Mendix files, from your working directory
* `build`: builds the buildpack, i.e. updates / fetches all dependencies that need to be in source control, including all runtime Python dependencies as wheels
* `upload`: uploads your working directory as `$BUILDPACK` to your Cloud Foundry testing cluster
* `install`: same as `build upload`

## Testing
We have split up tests into unit tests, which do not need a CF cluster to run, and integration tests, which do.

All tests applications deployed have a prefix so that the test script can clean up before and after any applications that are left behind. However, this limits the number or runs into the same org and space to one (1).

To overcome this, you can specify `TEST_PREFIX` as environment variable to change the naming of the test apps. `TEST_PREFIX` defaults to `ops`. 

## Running Tests
To run all the tests locally you need to do is to go to the root folder and run the following command:

```
make test
```

### Running Unit Tests
To run the unit (offline) tests only, run the following command:

```
make test_unit
```

### Running Integration Tests
To run the integration (online) tests only, run the following command:

```
make test_integration
```

If your tests fail, be sure to clean up the Cloud Foundry environment with:

```
make clean_cf
```
