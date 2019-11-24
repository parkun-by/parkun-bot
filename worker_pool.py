class WorkerPool:
    def __init__(self, logger):
        self.queue = set()
        self.logger = logger

    def add_worker(self, name: str) -> None:
        self.queue.add(name)
        self.logger.info(f'Новое состояние воркеров - {str(self.queue)}')

    def delete_worker(self, name: str) -> None:
        try:
            self.queue.remove(name)
            self.logger.info(f'Новое состояние воркеров - {str(self.queue)}')
        except KeyError:
            pass

    def pop_worker(self) -> str or None:
        try:
            worker = self.queue.pop()
            self.logger.info(f'Новое состояние воркеров - {str(self.queue)}')
            return worker
        except KeyError:
            return None
