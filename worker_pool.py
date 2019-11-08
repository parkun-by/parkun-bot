class WorkerPool:
    def __init__(self):
        self.queue = set()

    def add_worker(self, name: str) -> None:
        self.queue.add(name)

    def delete_worker(self, name: str) -> None:
        try:
            self.queue.remove(name)
        except KeyError:
            pass

    def pop_worker(self) -> str or None:
        try:
            return self.queue.pop()
        except KeyError:
            return None
