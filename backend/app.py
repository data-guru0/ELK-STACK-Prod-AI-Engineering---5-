import logging
import random
import sys
import threading
import time

from flask import Flask, jsonify

app = Flask(__name__)

logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s backend: %(message)s",
)
log = logging.getLogger("backend")

ITEMS = ["widget", "gadget", "gizmo", "doohickey"]


@app.get("/")
def index():
    log.info("health check ok")
    return jsonify(service="backend", status="ok")


@app.get("/api/orders")
def orders():
    item = random.choice(ITEMS)
    delay_ms = random.randint(5, 400)
    if delay_ms > 300:
        log.warning("order for %s took %dms (slow)", item, delay_ms)
    else:
        log.info("order placed for %s (%dms)", item, delay_ms)
    return jsonify(item=item, delay_ms=delay_ms)


@app.get("/api/error")
def error():
    # Deliberate failure endpoint used to demo error-tracking in Kibana.
    log.error("order processing failed: payment gateway timeout")
    return jsonify(error="payment gateway timeout"), 500


def heartbeat():
    while True:
        log.info("backend heartbeat: %d orders/min avg", random.randint(1, 50))
        time.sleep(5)


threading.Thread(target=heartbeat, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
