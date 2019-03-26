Testing the BuildPack
=====

To modify the build pack code [pyenv](https://github.com/pyenv/pyenv) in combination with [pyenv-virtualenv](https://github.com/pyenv/pyenv-virtualenv) can be used to create a local sandbox to develop in. Before running the tests some dependencies need to be installed which you find in `tests/requirements.txt`.

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

By default the test asumes you pushed your changes to a public git repository. The definitive
url is based on the branch you are using. The following can be done to change the default
location of the build pack:

* `TRAVIS_BRANCH`: this will take another git branch then you are working in
* `BUILDPACK_REPO`: this wil take another git repo as based. Usefull when the changes
are pushed to you private account
* `BUILDPACK`: this can be any buildpack reference. A git repo or the name of a
build pack uploaded to the Cloud Foundry cluster. This can be used if you want to test
you changes but don't want to make it public yet.


To run all the tests locally you need to do is to go to the root folder.

```
make test
```

To run a singe test take look at `run.sh`, e.g. you need to PYTHONPATH.
