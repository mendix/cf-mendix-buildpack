# Mendix Buildpack Development

This document describes best practices of developing the Mendix Buildpack. Use in conjunction with [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Buildpack Structure

The buildpack project features the following directories:

* `bin` : Cloud Foundry buildpack lifecycle scripts, utility scripts and binaries live here
* `buildpack` : All Python code lives here, this is the home of the main buildpack module. Entry points are `stage.py` and `start.py`
* `dev` : Code for local development and CI lives here
* `etc` : Configuration templates for e.g. nginx and M2EE live here
* `lib` : A forked version of M2EE Tools suited for the cloud lives here, used for working with the Mendix Runtime
* `tests` : All test code lives here

The following directories are not included in the repository, but are used in the development process:

* `build` : Working directory for building the buildpack
* `dist` : The final build artifact lives here
* `vendor` : All [vendorized dependencies](#vendoring-external-dependencies) live here

## Prerequisites

The buildpack is a Python project, and you must have some experience in Python, `bash` and the `make` system to develop.

For developing the buildpack, you must set up the following:

* A shell / terminal of your choice
* [Docker](https://www.docker.com/)
* The [Cloud Foundry CLI](https://docs.cloudfoundry.org/cf-cli/install-go-cli.html) and the [`cf-local`](https://github.com/cloudfoundry-incubator/cflocal) plugin
* A [`pyenv virtualenv`](https://github.com/pyenv/pyenv-virtualenv) virtual environment (or you can choose to develop in a Docker container)

### Installing `pyenv`

[`pyenv`](https://github.com/pyenv/pyenv) in combination with [`pyenv-virtualenv`](https://github.com/pyenv/pyenv-virtualenv) can be used to create a local Python virtual environment to develop in. Note that you'll have to create an environment with the latest version of Python 3.10 - the default in the Cloud Foundry root filesystem ( `cflinuxfs4` ) we use to deploy applications on.

### Developing in Docker

As an alternative to running Python on your host you can run it in a Docker container. To do this:

* Set up required environment variables
* Go to the `dev/` directory
* Run `./start_dev_environment.sh`

This will start the Docker container with preinstalled Python and provide you with an interactive shell.
The project folder will be mapped to the current folder in the Docker container, so if you edit files on your host, the changes will be immediately available in the container.

### Installing testing and linting requirements

The buildpack makes use of the `make` system. For dependency management, `pip-compile` is used under the hood.

A few `make` targets to use are:

* `vendor` : downloads the Python runtime dependencies as wheels into `build/vendor/wheels`, and copies over vendorized dependencies to the `build/vendor/`
* `install_requirements` : installs all requirements and generates `requirements.txt`

**Never change the `requirements*.txt` files directly!** Use `requirements*.in` to that.

### Setting up your environment

For integration tests, you need to have installed the prerequisites. Once you have those in place, you can set up the following environment variables:

```shell
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

```shell
make test
```

### Running Unit Tests

To run the unit (offline) tests only, run the following command:

```shell
make test_unit
```

### Running Integration Tests

To run the integration (online) tests only, run the following command:

```shell
make test_integration
```

You can keep watch on the tests with regular Docker commands such as `docker ps` .

To run one or more separate tests do:

```shell
make test_integration TEST_FILES='file1, file2'
```

## Running an application via a Command Line Interface (CLI)

As extension of the integration tests, a Command Line Interface (CLI) is available. This CLI enables you to run an arbitrary MDA with `cf-local` without having to do the heavy lifting yourself.
The CLI loosely follows the Docker CLI commands for `run` , `rm` and `logs` .

The CLI can be accessed by running the following command from the project root:

```shell
tests/integration/runner.py
```

The CLI features a help prompt to get you started:

```shell
tests/integration/runner.py --help
```

An example that runs the `myapp` application with a PostgreSQL database container and two environment variables:

```shell
tests/integration/runner.py run --name myapp --with-db -e ENV1=VALUE1 -e ENV2=VALUE2 myapp.mda
```

After running the application, standard Docker commands and Docker tooling can be used to manipulate the application container(s).

## Managing Dependencies

The buildpack includes two types of dependencies:

* **Python dependencies**. These are used to glue together everything required to run Mendix applications with the buildpack.
* **External dependencies**. These dependencies are required to run the Mendix applications deployed with the buildpack.

### Managing Python Dependencies

Python dependencies are managed by [`pip-tools`](https://github.com/jazzband/pip-tools). They are specified in [`requirements.in`](requirements.in) (general dependencies) and [`requirements-dev.in`](requirements-dev.in) (dependencies specific for developing and testing). `pip-tools` converts these files into the well-known [`requirements.txt`](requirements.txt).

All Python dependencies are automatically packaged as part of the build process. If the dependencies are not included in a release package, they are downloaded during the buildpack staging phase.

**Note: `requirements.txt` should not be edited manually. Please read on to learn how to work with `requirements.in` and `pip-tools`.**

To convert `requirements.in` into `requirements.txt`, run the following command:

```shell
make requirements
```

To install all requirements into your local development environment, run the following command:

```shell
make install_requirements
```

### Managing External Dependencies

The buildpack specifies all external dependencies in [`dependencies.yml`](dependencies.yml). This file contains all information required to resolve and download an external dependency.
How this process works is best explained by an example:

```yaml
dependencies:
    foo:
        bar:
            version: 1.0.0
            artifact: some_location/some_archive-{{ version }}.tar.gz
```

The YAML file can contain templated fields in the [Jinja2](https://jinja.palletsprojects.com/) template language. The `{{ version }}` is an example of this language.

#### Specifying an External Dependency

This YAML snippet contains information about the dependency name (composed of a "group" and a name), a dependency version and the artifact that should be downloaded for that dependency. This snippet is used in the dependency resolution process to form a dependency object. The dependency object is formed recursively, and any fields in a "parent" for a dependency will be propagated downwards, with [some exceptions](#special--reserved-fields).

The result of this example is the following Python dictionary:

```python
{
    "foo.bar": {
        "version": "1.0.0",
        "artifact": "some_location/some_archive-{{ version }}.tar.gz",
        "name": ["foo", "bar"]
    }
}
```

#### Resolving an External Dependency

This dependency object is used to resolve and download the artifact. This happens in [`util.py`](buildpack/util.py), specifically in `resolve_dependency()`.

The resolution function is used by all buildpack components, and performs the following steps:

1. Find the dependency with the specified name in the list of dependencies. The name is composed of all the YAML sections, separated by `.`, and is used as a key in the dependency list. For the example: `foo.bar`.
2. Render any unparsed fields (in the example: `artifact`) with:
   * The fields present in the dependency object itself (in the example: `version`). For the example, this will result in `some_location/some_archive-1.0.0.tar.gz`.
   * The fields specified in a `overrides` dictionary. These override any values present in the dependency object, or will extend the dependency object when they are not present.
3. Compose the URL for the `artifact` field:
   * If the URL starts with `http(s)://`, don't change it
   * If the URL starts with a `/`, prepend the blob store root URL (specified in code or in the `BLOBSTORE` environment variable).
   * Else, prepend the blob store root URL and `mx-buildpack/`. For the example, this results in `https://cdn.mendix.com/mx-buildpack/some_location/some_archive-1.0.0.tar.gz`.
4. Delete any other versions of the file in the URL from the cache. Alternative names can be specified in an `alias` field.
5. Download and optionally unpack the file in the URL to a specified location:
   * Check the [`vendor` directory](#vendoring-external-dependencies) if the file is present. If so, retrieve from there
   * Check the Cloud Foundry cache directory if the file is present. If so, retrieve from there
   * If not, download from the Mendix CDN

Dependencies can also be retrieved individually, as dependency information could be required outside of the staging process. To do so, use the `get_dependency()` function in `util.py`.

#### Special / Reserved Fields

A number of fields in a dependency object are reserved / special fields:

* `artifact` should always be present and contains the location of the artifact that should be downloaded
* `alias` contains alternative names for the artifact and is used to delete other / older versions from the Cloud Foundry cache for the application. It is not part of the dependency matrix, and can be a list of strings or a string value.
* `name` contains the list of YAML sections that compose the dependency key. It is not part of the dependency matrix.
* `managed` indicates whether the source of the dependency is managed by the authors of this buildpack
* `version` indicates that an artifact is versioned. The presence of this field indicates that earlier versions of an artifact can be removed from the buildpack cache during dependency resolution.
* `*_key` fields contain the key of dictionary fields which are recursed into the dependency graph leaf nodes. See [here](#advanced-examples) for an example.
* `cpe`, `purl` and `bom_*` fields contain information to generate a [Software Bill of Materials (SBOM)](#generating-an-sbom-for-external-dependencies).

All other fields are free format.

#### Advanced Examples

The following example **propagates fields** downwards into the resulting dependency dictionary:

```yaml
dependencies:
    foo:
        version: 1.0.0
        artifact: "some_location/some_archive-{{ type }}-{{ version }}.tar.gz"
        bar:
            type: "fizz"
        baz:
            type: "buzz"
```

The result of this example is the following Python dictionary:

```python
{
    "foo.bar": {
        "artifact": "some_location/some_archive-{{ type }}-{{ version }}.tar.gz",
        "type": "fizz",
        "version": "1.0.0",
        "name": ["foo", "bar"]
    },
    "foo.baz": {
        "artifact": "some_location/some_archive-{{ type }}-{{ version }}.tar.gz",
        "type": "buzz",
        "version": "1.0.0",
        "name": ["foo", "baz"]
    }
}
```

The following example renders a **dependency matrix**, and uses field values in YAML sections:

```yaml
dependencies:
    foo:
        "{{ type }}-{{ version_key }}":
            artifact: "some_location/some_archive-{{ type }}-{{ version }}.tar.gz"
            type:
                - "fizz"
                - "buzz"
            version:
                - "1": 1.0.0
                - "2": 2.0.0
```

The result of this example is the following Python dictionary:

```python
{
    "foo.fizz-1": {
        "artifact": "some_location/some_archive-{{ type }}-{{ version }}.tar.gz",
        "type": "fizz",
        "version": "1.0.0",
        "version_key": "1",
        "name": ["foo", "fizz-1"]
    },
    "foo.buzz-1": {
        "artifact": "some_location/some_archive-{{ type }}-{{ version }}.tar.gz",
        "type": "buzz",
        "version": "1.0.0",
        "version_key": "1",
        "name": ["foo", "buzz-1"]
    },
    "foo.fizz-2": {
        "artifact": "some_location/some_archive-{{ type }}-{{ version }}.tar.gz",
        "type": "fizz",
        "version": "2.0.0",
        "version_key": "2",
        "name": ["foo", "fizz-2"]
    },
    "foo.buzz-2": {
        "artifact": "some_location/some_archive-{{ type }}-{{ version }}.tar.gz",
        "type": "buzz",
        "version": "2.0.0",
        "version_key": "2",
        "name": ["foo", "buzz-2"]
    },
}
```

A couple of things happened in this example:

* The `type` field and `version` field were used to compose a 2x2 matrix of dependencies.
* The `type` field was literally propagated; the `version` field was a dictionary and propagated into a `version` field (containing the dictionary value) and `version_key` field (containing the dictionary key).
* The artifact name was rendered using these fields

#### Listing External Dependencies

To print a list of all managed external dependencies, run the following command:

```shell
make list_external_dependencies
```

#### Generating an SBOM for External Dependencies

For some use cases, an official Software Bill of Materials (SBOM) is required. The following command generates a [CycloneDX](https://cyclonedx.org/) 1.4 JSON SBOM:

```shell
make generate_software_bom
```

An essential part of every SBOM is including identifiers for dependencies. Currently, there are two identifiers supported in the following fields:

* `cpe`: Common Platform Enumeration (CPE) identifier. NIST maintains a [list of CPEs](https://nvd.nist.gov/products/cpe) to which vulnerabilities can be linked.
* `purl`: Package URL (PURL). This specification can be found [here](https://github.com/package-url/purl-spec).

Additionally, extra information can be included in the BOM, or override existing information. To do so, include a `bom_<key>` field, with `key` being the name of the information you are trying to add and override. The SBOM will contain this information, minus the `bom_` prefix.

### Vendoring External Dependencies

You can include ("vendor in") any external dependency you want in your build by adding it to `vendor/` directory. This will ensure that the dependency is packaged in the buildpack artifact. This is especially useful for testing dependencies you have built yourself locally, but are not available online yet.

The dependency resolution will detect dependencies in `vendor/` regardless of subdirectory. The only condition is that you use the same file name as the dependency you would like to vendor in instead of getting it online.
