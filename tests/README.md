TestCases for BuildPack
=====

The following ENV VARS are needed in order to run tests locally.

```
export CF_ENDPOINT="https://api.cf.example.com"
export CF_USER="username"
export CF_PASSWORD="p455w0rd"
export CF_ORG="testorganization"
export CF_SPACE="cispace"
export CF_DOMAIN="cf-test.example.com"
export MX_PASSWORD="sebaiNgooyiyoh9cheuquueghoongo@!"
```

To run the tests locally all you need to do is to go to the root folder.

    cd tests && bash run.sh
