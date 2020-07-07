PACKAGE_NAME := buildpack
PREFIX=$(shell p='$(TEST_PREFIX)'; echo "$${p:-test}")
TEST_PROCESSES := $(if $(TEST_PROCESSES),$(TEST_PROCESSES),2)
TEST_FILES := $(if $(TEST_FILES),$(TEST_FILES),tests/integration/test_*.py)

.PHONY: vendor
vendor: download_wheels

.PHONY: download_wheels
download_wheels: requirements
	rm -rf vendor/wheels
	mkdir -p vendor/wheels
	pip3 download -d vendor/wheels/ --only-binary :all: pip==20.1.1 setuptools==47.3.1
	pip3 download -d vendor/wheels/ --no-deps --platform manylinux1_x86_64 --python-version 36 -r requirements.txt

.PHONY: create_build_dirs
create_build_dirs:
	mkdir -p build
	mkdir -p dist

.PHONY: build
build: create_build_dirs vendor write_commit
	# git archive -o source.tar HEAD
	git ls-files | tar Tcf - source.tar
	tar xf source.tar -C build/
	rm source.tar
	cd build && rm -rf .gitignore .pylintrc .travis.yml* Makefile *.in tests/ dev/
	cd build && zip -r  -9 ../dist/${PACKAGE_NAME}.zip .

.PHONY: install_piptools
install_piptools:
	pip3 install --upgrade pip setuptools
	pip3 install pip-tools==5.2.1

.PHONY: install_requirements
install_requirements: install_piptools requirements
	pip-sync requirements-all.txt

.PHONY: requirements
requirements: install_piptools
	pip-compile requirements*.in -o requirements-all.txt
	pip-compile requirements.in

.PHONY: lint
lint:
	black --line-length=79 --check --diff $(PACKAGE_NAME) lib/m2ee/* tests/*/
	pylint --disable=W,R,C $(PACKAGE_NAME) lib/m2ee/* tests/*/

.PHONY: clean
clean:
	rm -rf build/ dist/
	rm -rf .coverage
	rm -rf .pytest_cache
	rm -rf .mypy_cache
	rm -rf $(PACKAGE_NAME).egg-info
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
	black --line-length=79 $(PACKAGE_NAME) tests lib/m2ee/*

.PHONY: write_commit
write_commit:
	git rev-parse --short HEAD > build/.commit
