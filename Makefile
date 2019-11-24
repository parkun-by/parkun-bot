SHELL:=/bin/bash

py_env:
	rm -rf .venv/
	python3 -m venv .venv; \
	( \
		source .venv/bin/activate \
		pip install --upgrade pip; \
		pip install --upgrade wheel; \
		pip install -r requirements.txt; \
	)

start_dev_env:
	docker-compose -f env_parkun/docker-compose-dev-env.yml up -d --build

stop_dev_env:
	docker-compose -f env_parkun/docker-compose-dev-env.yml down

start_prod_env:
	docker-compose -f env_parkun/docker-compose-prod-env.yml up -d --build

stop_prod_env:
	docker-compose -f env_parkun/docker-compose-prod-env.yml down

start_bot:
	docker-compose -f env_parkun/docker-compose-bot.yml up -d --build

stop_bot:
	docker-compose -f env_parkun/docker-compose-bot.yml down

stop_all: stop_bot stop_dev_env stop_prod_env
