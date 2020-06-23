PACKAGE_NAME := buildpack
SHELL=bash
PREFIX=$(shell p='$(TEST_PREFIX)'; echo "$${p:-ops}")

XARGS := xargs
CUT := cut
UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Darwin)
	XARGS := gxargs
	CUT := gcut
	ifeq ($(shell which $(XARGS)), "")
		$(error Cannot find gxargs and gcut, you might need to install coreutils and findutils with Brew)
	endif
endif

.PHONY: login
login:
	@cf login -a ${CF_ENDPOINT} -u ${CF_USER} -p ${CF_PASSWORD} -o ${CF_ORG} -s ${CF_SPACE}

.PHONY: clean_cf
clean_cf:
	-@$(shell cf apps 2>&1 | grep ^$(PREFIX) | $(CUT) -f 1 -d ' ' | $(XARGS) -n 1 -P 5 --no-run-if-empty cf delete -r -f | grep -v 'Deleting' | grep -v 'OK' || true)
	-@$(shell cf s 2>&1 |  grep ^$(PREFIX) | $(CUT) -f 1 -d ' ' | $(XARGS) -n 1 -P 5 --no-run-if-empty cf ds -f $$service | grep -v 'Deleting' | grep -v 'OK' || true)
	-@$(shell cf delete-orphaned-routes -f 2>&1 | grep deleting || true)
	@echo "Completed CF environment cleanup"	

.PHONY: vendor
vendor: download_wheels

.PHONY: download_wheels
download_wheels: install_build_requirements
	rm -rf vendor/wheels
	mkdir -p vendor/wheels
	pip3 download -d vendor/wheels/ --only-binary :all: pip==20.1.1 setuptools==47.3.1
	pip3 download -d vendor/wheels/ --no-deps --platform manylinux1_x86_64 --python-version 36 -r requirements.txt

.PHONY: build
build: vendor

.PHONY: upload
upload:
	cf delete-buildpack -f ${BUILDPACK}
	cf create-buildpack ${BUILDPACK} . 30

.PHONY: install
install: build upload

.PHONY: install_piptools
install_piptools:
	pip3 install pip-tools==5.2.1

.PHONY: install_lint_requirements
install_lint_requirements: install_piptools
	pip-compile requirements-lint.in
	pip3 install -r requirements-lint.txt

.PHONY: lint
lint:
	black --line-length=79 --check --diff $(PACKAGE_NAME) lib/m2ee/* tests/*/
	pylint --disable=W,R,C $(PACKAGE_NAME) tests/*/

.PHONY: install_test_requirements
install_test_requirements: install_piptools
	pip-compile requirements-test.in
	pip3 install -r requirements-test.txt

.PHONY: clean
clean:
	rm -rf .coverage
	rm -rf .pytest_cache
	rm -rf .mypy_cache
	rm -rf $(PACKAGE_NAME).egg-info
	rm -rf pip-wheel-metadata
	rm -f *.mda *.mpk
	find . -regex ".*__pycache__.*" -delete
	find . -regex "*.py[co]" -delete

.PHONY: install_build_requirements
install_build_requirements: install_piptools
	pip-compile requirements.in
	pip3 install -r requirements.txt

.PHONY: test_unit
test_unit:
	export PYTHONPATH=.:lib/
	nosetests --verbosity=3 --processes=10 --process-timeout=3600 --with-timer --timer-no-color tests/unit/test_*.py

.PHONY: test_integration
test_integration:
	export PYTHONPATH=.:lib/
	nosetests --verbosity=3 --processes=10 --process-timeout=3600 --with-timer --timer-no-color tests/integration/test_*.py

.PHONY: test
test: test_unit test_integration

.PHONY: format
format:
	black --line-length=79 $(PACKAGE_NAME) tests lib/m2ee/*
