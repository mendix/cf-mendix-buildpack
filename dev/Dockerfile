FROM --platform=linux/amd64 python:3.10-slim

WORKDIR /app

COPY ./requirements.in ./
COPY ./requirements-dev.in ./
COPY ./Makefile ./

RUN apt-get update \
 && apt-get upgrade -y \
 && apt-get install -y make wget gnupg ca-certificates curl \
 && make install_requirements \
 && install -m 0755 -d /etc/apt/keyrings \
 && curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
 && chmod a+r /etc/apt/keyrings/docker.gpg \
 && echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian bookworm stable" > /etc/apt/sources.list.d/docker.list \
 && wget -q -O - https://packages.cloudfoundry.org/debian/cli.cloudfoundry.org.key | gpg --dearmor -o /usr/share/keyrings/cloudfoundry.gpg \
 && echo "deb [signed-by=/usr/share/keyrings/cloudfoundry.gpg] https://packages.cloudfoundry.org/debian stable main" | tee /etc/apt/sources.list.d/cloudfoundry-cli.list \
 && apt-get update \
 && apt-get install -y cf-cli docker-ce-cli zip

RUN cf install-plugin -f cflocal