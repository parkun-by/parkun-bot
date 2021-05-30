FROM python:3.9.5-buster

WORKDIR /usr/src/app

COPY requirements.txt ./
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

CMD [ "./env_docker/parkun_bot/entrypoint.sh" ]
