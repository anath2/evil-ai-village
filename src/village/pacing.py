"""Shared HTTP-attempt pacing, including retries, with an auditable dispatch log."""
import json
from pathlib import Path
import threading
import time


class RequestPacer:
    def __init__(self, interval: float, path: Path):
        if interval <= 0:
            raise ValueError('Request spacing must be positive')
        self.interval = interval
        self.path = path
        self.lock = threading.Lock()
        self.next_dispatch = 0.0
        self.attempts = 0
        path.parent.mkdir(parents=True, exist_ok=True)

    def __call__(self, request):
        with self.lock:
            time.sleep(max(0.0, self.next_dispatch - time.monotonic()))
            now = time.monotonic()
            self.next_dispatch = now + self.interval
            self.attempts += 1
            with self.path.open('a') as stream:
                stream.write(json.dumps({'ts': time.time(), 'monotonic': now,
                                         'model': json.loads(request.content).get('model')}) + '\n')
