py_env:
	rm -rf env/
	python -m venv env; \
	source env/bin/activate
	pip install --upgrade pip
	pip install -r requirements.txt

start_extra_services:
	docker-compose -f env_parkun/docker-compose.yml up -d --build

stop_extra_services:
	docker-compose -f env_parkun/docker-compose.yml down
