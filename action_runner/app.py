from __future__ import annotations

import threading
from http.server import ThreadingHTTPServer

from .config import HOST, PORT
from .http_handler import ActionRunnerHandler
from .rule_loader import load_rules
from .runtime import LOADED_RULES
from .scheduler import scheduler_loop
from .state import init_db
from .worker import executor_worker_loop, notify_worker_loop


def main() -> None:
    init_db()

    LOADED_RULES.clear()
    LOADED_RULES.extend(load_rules())

    executor_thread = threading.Thread(
        target=executor_worker_loop,
        name="executor-worker",
        daemon=True,
    )
    executor_thread.start()

    notify_thread = threading.Thread(
        target=notify_worker_loop,
        name="notify-worker",
        daemon=True,
    )
    notify_thread.start()

    scheduler_thread = threading.Thread(
        target=scheduler_loop,
        name="scheduler",
        daemon=True,
    )
    scheduler_thread.start()

    server = ThreadingHTTPServer((HOST, PORT), ActionRunnerHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
