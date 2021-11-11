PROJECT_NAME := $(if $(PROJECT_NAME),$(PROJECT_NAME),cf-mendix-buildpack)
PREFIX=$(shell p='$(TEST_PREFIX)'; echo "$${p:-test}")
TEST_PROCESSES := $(if $(TEST_PROCESSES),$(TEST_PROCESSES),2)
TEST_FILES := $(if $(TEST_FILES),$(TEST_FILES),tests/integration/test_*.py)
MAX_LINE_LENGTH = $(shell cat .pylintrc | grep max-line-length | cut -d '=' -f 2 | xargs)

PIP_TOOLS_VERSION = 6.4.0
PIP_VERSION = 21.3
PYTHON_PLATFORM := $(if $(PYTHON_PLATFORM),$(PYTHON_PLATFORM),manylinux2014_x86_64)
PYTHON_VERSION := $(if $(PYTHON_VERSION),$(PYTHON_VERSION),36)

.PHONY: vendor
vendor: create_build_dirs copy_vendored_dependencies download_wheels

.PHONY: copy_vendored_dependencies
copy_vendored_dependencies:
	cp -rf vendor build/

.PHONY: download_wheels
download_wheels: requirements
	rm -rf build/vendor/wheels
	mkdir -p build/vendor/wheels
	pip3 download -d build/vendor/wheels/ --only-binary :all: pip==${PIP_VERSION} setuptools wheel
	pip3 download -d build/vendor/wheels/ --no-deps --platform ${PYTHON_PLATFORM} --python-version ${PYTHON_VERSION} -r requirements.txt

.PHONY: create_build_dirs
create_build_dirs:
	mkdir -p build
	mkdir -p dist

.PHONY: build
build: create_build_dirs vendor write_commit
	# git archive -o source.tar HEAD
	git ls-files | tar Tcf - source.tar
	tar xf source.tar -C build/ --exclude=.commit
	rm source.tar
	cd build && rm -rf .github/ .gitignore .pylintrc .travis.yml* Makefile *.in tests/ dev/
	cd build && zip -r  -9 ../dist/${PROJECT_NAME}.zip .

.PHONY: install_piptools
install_piptools:
	pip3 install --upgrade pip==${PIP_VERSION} setuptools wheel
	pip3 install pip-tools==$(PIP_TOOLS_VERSION)

.PHONY: install_requirements
install_requirements: install_piptools requirements
	pip-sync requirements-all.txt

.PHONY: requirements
requirements: install_piptools
	pip-compile requirements*.in -o requirements-all.txt
	pip-compile requirements.in

.PHONY: write_commit
write_commit:
	git rev-parse --short HEAD > build/.commit

.PHONY: clean
clean:
	rm -f source.tar
	rm -rf build/ dist/
	rm -rf .coverage
	rm -rf .pytest_cache
	rm -rf .mypy_cache
	rm -rf buildpack.egg-info
	rm -rf pip-wheel-metadata
	rm -f *.mda *.mpk
	find . -regex ".*__pycache__.*" -delete
	find . -regex "*.py[co]" -delete

.PHONY: test_unit
test_unit:
	export PYTHONPATH=.:lib/
	nosetests --verbosity=3 --nocapture --with-timer --timer-no-color tests/unit/test_*.py

.PHONY: test_integration
test_integration: 
	export PYTHONPATH=.:lib/
	nosetests --verbosity=3 --nocapture --processes=${TEST_PROCESSES} --process-timeout=3600 --with-timer --timer-no-color ${TEST_FILES}

.PHONY: test
test: test_unit test_integration

.PHONY: format
format:
	black --line-length=${MAX_LINE_LENGTH} buildpack lib/m2ee/* tests/*/

.PHONY: lint
lint:
	black --line-length=${MAX_LINE_LENGTH} --check --diff buildpack lib/m2ee/* tests/*/
	pylint --disable=W,R,C buildpack lib/m2ee/* tests/*/
