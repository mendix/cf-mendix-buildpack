FROM --platform=linux/amd64 python:3.10

WORKDIR /app

COPY ./requirements.in ./
COPY ./requirements-dev.in ./
COPY ./Makefile ./

RUN make install_requirements
 
RUN apt-get update \
 && apt-get install -y wget gnupg \
 && wget -q -O - https://packages.cloudfoundry.org/debian/cli.cloudfoundry.org.key | gpg --dearmor -o /usr/share/keyrings/cloudfoundry.gpg \
 && echo "deb [signed-by=/usr/share/keyrings/cloudfoundry.gpg] https://packages.cloudfoundry.org/debian stable main" | tee /etc/apt/sources.list.d/cloudfoundry-cli.list \
 && apt-get update \
 && apt-get install -y cf-cli docker.io zip

RUN cf install-plugin -f cflocal
