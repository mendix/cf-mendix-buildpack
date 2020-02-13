# Testing the BuildPack
To modify the buildpack code, [pyenv](https://github.com/pyenv/pyenv) in combination with [pyenv-virtualenv](https://github.com/pyenv/pyenv-virtualenv) can be used to create a local sandbox to develop in. Before running the tests, some dependencies need to be installed. You can find these in `tests/requirements.txt`.

The following environment variables are needed in order to run tests locally.

```
export CF_ENDPOINT="https://api.cf.example.com"
export CF_USER="username"
export CF_PASSWORD="p455w0rd"
export CF_ORG="testorganization"
export CF_SPACE="cispace"
export CF_DOMAIN="cf-test.example.com"
export MX_PASSWORD="sebaiNgooyiyoh9cheuquueghoongo@!"
```

## Selecting the Buildpack Repo and Branch
By default, the test assumes you pushed your changes to a public git repository. The definitive
url is based on the branch you are using. The following can be done to change the default
location of the buildpack:

* `TRAVIS_BRANCH`: this will take another git branch then you are working in
* `BUILDPACK_REPO`: this wil take another git repo as based. Useful when the changes
are pushed to you private account
* `BUILDPACK`: this can be any buildpack reference. A git repo or the name of a
build pack uploaded to the Cloud Foundry cluster. This can be used if you want to test
you changes but don't want to make it public yet.


## Simultaneous Runs
All tests applications deployed have a prefix so that the test script can clean up before and after any applications that are left behind. However, this limits the number or runs into the same org and space to one (1).   
To overcome this, you can specify `TEST_PREFIX` as environment variable to change the naming of the test apps. `TEST_PREFIX` defaults to `ops`. 

## Running Tests

To run all the tests locally you need to do is to go to the root folder.

```
make test
```

To run a singe test, take a look at the `Makefile`.
