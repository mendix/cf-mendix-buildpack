# Mendix Buildpack Development

This document describes best practices of developing the Mendix Buildpack. Use in conjunction with [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Buildpack Structure

The buildpack features the following directories:

* `bin` : Cloud Foundry buildpack lifecycle scripts, utility scripts and binaries live here
* `buildpack` : All Python code lives here, this is the home of the main buildpack module. Entry points are `compile.py` and `start.py`
* `dev` : Code for local development and CI lives here
* `docs` : Extra documentation in Markdown format lives here
* `etc` : Configuration templates for e.g. nginx and M2EE live here
* `lib` : A forked version of M2EE Tools suited for the cloud lives here, used for working with the Mendix Runtime
* `tests` : All test code lives here
* `vendor` : All vendorized dependencies live here

## Prerequisites

The buildpack is a Python project, and you must have some experience in Python, `bash` and the `make` system to develop.

For developing the buildpack, you must set up the following:

* A shell / terminal of your choice
* [Docker](https://www.docker.com/)
* The [Cloud Foundry CLI](https://docs.cloudfoundry.org/cf-cli/install-go-cli.html) and the [`cf-local`](https://github.com/cloudfoundry-incubator/cflocal) plugin
* A [`pyenv virtualenv`](https://github.com/pyenv/pyenv-virtualenv) virtual environment (or you can choose to develop in a Docker container)

### Installing `pyenv`

[`pyenv`](https://github.com/pyenv/pyenv) in combination with [`pyenv-virtualenv`](https://github.com/pyenv/pyenv-virtualenv) can be used to create a local Python virtual environment to develop in. Note that you'll have to create an environment with the latest version of Python 3.6 - the default in the Cloud Foundry root filesystem (`cflinuxfs3`) we use to deploy applications on.

### Developing in `Docker`

As an alternative to running Python on your host you can run it in a Docker container. To do this:

* Set up required environment variables
* Go to the `dev/` directory
* Run `./run-locally.sh`
This will start the Docker container with preinstalled Python and provide you with an interactive shell.
The project folder will be mapped to the current folder in the Docker container, so if you edit files on your host, the changes will be immediately available in the container.

### Installing testing and linting requirements

The buildpack makes use of the `make` system. For dependency management, `pip-compile` is used under the hood.

A few `make` targets to use are:

* `vendor` : downloads the Python runtime dependencies as wheels into `vendor/wheels`
* `install_requirements` : installs all requirements and generates requirements.txt

**Never change the `requirements*.txt` files directly!** Use `requirements*.in` to that.

### Setting up your environment

For integration tests, you need to have installed the prerequisites. Once you have those in place, you can set up the following environment variables:

``` shell
export TEST_PREFIX="<prefix identifying your test run; default=test>"
export TEST_PROCESSES="<amount of simultaneous tests to run; default=2>"
export TEST_HOST="<custom host the tests will use to connect to dependencies; default=host.docker.internal>"
export TEST_MEMORY="<memory a test app container gets; default=1G>"
export TEST_DISK="<disk space a test app container gets; default=1G>"
```

## Building

To ensure that your CF cluster has the buildpack you're developing available, use the following `make` targets:

* `clean` : removes all the nasties, including leftover Mendix files, from your working directory
* `lint` : ensures that code adheres to our standards
* `build` : builds the buildpack, i.e. updates / fetches all dependencies that need to be in source control, including all runtime Python dependencies as wheels, and compresses it to `dist/`

## Testing

We have split up tests into unit tests, which do not need to fully start a Mendix application, and integration tests, which do.

## Running Tests

To run all the tests locally you need to do is to go to the root folder and run the following command:

``` shell
make test
```

### Running Unit Tests

To run the unit (offline) tests only, run the following command:

``` shell
make test_unit
```

### Running Integration Tests

To run the integration (online) tests only, run the following command:

``` shell
make test_integration
```

You can keep watch on the tests with regular Docker commands such as `docker ps`.

To run one or more separate tests do:

``` shell
make test_integration TEST_FILES='file1, file2'
```
