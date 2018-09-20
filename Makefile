test: lint
	cd tests && bash run.sh

lint:
	flake8 --exclude .git,__pycache__,lib/certifi,lib/idna,lib/psycopg2,lib/urllib3,lib/chardet,lib/httplib2,lib/requests,lib/yaml
	black --check --diff .
