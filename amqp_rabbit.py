import aio_pika
import config


class Rabbit:
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
