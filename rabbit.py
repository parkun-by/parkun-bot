import aio_pika
import config
import json


class Rabbit:
    def __init__(self):
        pass

    async def init(self, loop):
        self.connection = await aio_pika.connect_robust(
            config.RABBIT_ADDRESS,
            loop=loop
        )

    async def send(self, body):
        async with self.connection:
            self.channel = await self.connection.channel()
            self.exchange = await self.channel.declare_exchange(
                config.RABBIT_EXCHANGE,
                type='fanout',
                durable='true')

            await self.exchange.publish(
                aio_pika.Message(body=json.dumps(body).encode()),
                routing_key='violation')
