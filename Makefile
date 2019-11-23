py_env:
	rm -rf env/
	python -m venv env; \
	source env/bin/activate
	pip install --upgrade pip
	pip install -r requirements.txt

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
