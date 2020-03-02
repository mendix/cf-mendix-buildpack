SHELL=bash
PREFIX=$(shell p='$(TEST_PREFIX)'; echo "$${p:-ops}")

.PHONY: login clean clean-cf clean-files run-test test lint

login:
	@cf login -a ${CF_ENDPOINT} -u ${CF_USER} -p ${CF_PASSWORD} -o ${CF_ORG} -s ${CF_SPACE}

clean: clean-cf clean-files

clean-cf:
	@echo "Cleaning up CF environment..."
	$(shell cf apps 2>&1 | awk -v s="$(PREFIX)" 'index($$0, s) == 1' | cut -f 1 -d ' ' | xargs -n 1 cf delete -r -f  | grep -v 'OK' || true)
	$(shell cf s 2>&1 | awk -v s="$(PREFIX)" 'index($$0, s) == 1' | cut -f 1 -d ' ' | xargs -n 1 cf ds -f | grep -v 'OK' || true)
	@cf delete-orphaned-routes -f 2>&1 | grep -i Deleting || true
	@echo "Completed CF environment cleanup"	

clean-files:
	@rm -f *.mda
	@rm -f *.mpk
	@echo "Deleted leftover MPK and MDA filess"

test:
	export PYTHONPATH=.:lib/
	nosetests --verbosity=3 --processes=10 --process-timeout=3600 --with-timer --timer-no-color tests/usecase/test_*.py

lint:
	flake8 --exclude .git,__pycache__,lib/backoff,lib/certifi,lib/idna,lib/psycopg2,lib/urllib3,lib/chardet,lib/httplib2,lib/requests,lib/yaml
	black --target-version py34 --check --diff .

install:
	cf delete-buildpack -f ${BUILDPACK}
	cf create-buildpack ${BUILDPACK} . 30
