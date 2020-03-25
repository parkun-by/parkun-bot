FROM rabbitmq:3.8.0-management-alpine

ADD rabbitmq.conf /etc/rabbitmq/
ADD definitions.json /etc/rabbitmq/

RUN rabbitmq-plugins enable rabbitmq_management