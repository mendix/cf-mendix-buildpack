FROM python:3.6

WORKDIR /app

COPY ./requirements.in ./
COPY ./requirements-dev.in ./
COPY ./Makefile ./

RUN make install_requirements

RUN wget -q -O - https://packages.cloudfoundry.org/debian/cli.cloudfoundry.org.key | apt-key add - \
 && echo "deb https://packages.cloudfoundry.org/debian stable main" | tee /etc/apt/sources.list.d/cloudfoundry-cli.list \
 && apt-get update \
 && apt-get install -y cf-cli docker

RUN cf install-plugin -f cflocal
