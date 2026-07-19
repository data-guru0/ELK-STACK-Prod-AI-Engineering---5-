import logging
import random
import sys
import time

logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s worker: %(message)s",
)
log = logging.getLogger("worker")

TASKS = ["resize-image", "send-email", "generate-invoice", "sync-inventory"]


def run():
    while True:
        task = random.choice(TASKS)
        duration = random.uniform(0.2, 2.0)
        time.sleep(duration)
        roll = random.random()
        if roll < 0.08:
            log.error("task %s failed: unexpected exception", task)
        elif roll < 0.20:
            log.warning("task %s retried after timeout (%.1fs)", task, duration)
        else:
            log.info("task %s completed in %.1fs", task, duration)


if __name__ == "__main__":
    run()
