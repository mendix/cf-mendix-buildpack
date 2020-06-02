FROM python:3.6.9

WORKDIR /home/vcap/app

COPY ./requirements.in ./
COPY ./requirements-lint.in ./
COPY ./requirements-test.in ./
COPY ./Makefile ./

RUN make install_piptools \
 && pip-compile requirements.in \
 && pip-compile requirements-lint.in \
 && pip-compile requirements-test.in \
 && pip3 install -r requirements.txt \
 && pip3 install -r requirements-lint.txt \
 && pip3 install -r requirements-test.txt \
 && pip3 install nose \
 && pip3 install nose-timer \
 && pip-sync requirements.txt requirements-test.txt requirements-lint.txt

RUN wget -q -O - https://packages.cloudfoundry.org/debian/cli.cloudfoundry.org.key | apt-key add - \
 && echo "deb https://packages.cloudfoundry.org/debian stable main" | tee /etc/apt/sources.list.d/cloudfoundry-cli.list \
 && apt-get update \
 && apt-get install cf-cli
