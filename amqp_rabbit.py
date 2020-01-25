import aio_pika
import config
import asyncio


class Rabbit:
    def __init__(self, logger):
        self.logger = logger

    async def start(self, loop, callback):
        try:
            await self.connect(loop, callback)
        except Exception as exc:
            self.logger.info(f'Fail. Trying reconnect Rabbit. {exc}')
            self.logger.exception(exc)
            await asyncio.sleep(2)
            await self.start(loop, callback)
        except ConnectionRefusedError:
            await asyncio.sleep(2)
            await self.connect(loop, callback)

    async def connect(self, loop, callback) -> None:
        self.connection = await aio_pika.connect_robust(
            config.RABBIT_AMQP_ADDRESS,
            loop=loop
        )

        async with self.connection:
            # Creating channel
            channel = await self.connection.channel()

            # Declaring queue
            queue = await channel.declare_queue(
                config.RABBIT_QUEUE_STATUS,
                auto_delete=False,
                durable=True
            )

            while True:
                async with queue.iterator() as queue_iter:
                    async for message in queue_iter:
                        async with message.process():
                            await callback(message.body.decode())
