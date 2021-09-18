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

start_dev:
	docker-compose -f env_docker/docker-compose.yml up -d --build

stop_dev:
	docker-compose -f env_docker/docker-compose.yml down

give_rights:
	sudo chmod 777 /tmp/temp_files_parkun
