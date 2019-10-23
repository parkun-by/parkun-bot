import aio_pika
import config
import asyncio


class Rabbit:
    async def start(self, loop, callback):
        try:
            await self.connect(loop, callback)
        except:
            print('Fail. Trying reconnect Rabbit.')
            await asyncio.sleep(2)
            await self.start(loop, callback)

    async def connect(self, loop, callback):
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
