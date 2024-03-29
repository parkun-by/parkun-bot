SHELL:=/bin/bash

venv:
	rm -rf .venv/
	python -m venv .venv; \
	( \
		source .venv/bin/activate \
		pip install --upgrade pip; \
		pip install --upgrade wheel; \
		pip install -r requirements.txt; \
	)

start_env:
	docker-compose -f env_docker/docker-compose.yml up -d --build

stop_env:
	docker-compose -f env_docker/docker-compose.yml down

give_rights:
	sudo chmod 777 /tmp/temp_files_parkun

NAME   := skaborik/parkun_bot
TAG    := $$(git describe --tags --abbrev=0)
IMG    := ${NAME}:${TAG}

build:
	@docker build -t ${IMG} .

push:
	@docker push ${IMG}
