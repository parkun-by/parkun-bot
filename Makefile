py_env:
	rm -rf env/
	python -m venv env; \
	source env/bin/activate
	pip install --upgrade pip
	pip install -r requirements.txt

extra_env:
	docker-compose -f env_parkun/docker-compose.yml up -d

stop_extra_env:
	docker-compose -f env_parkun/docker-compose.yml down
