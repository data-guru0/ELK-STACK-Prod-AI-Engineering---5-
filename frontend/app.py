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
    format="%(asctime)s %(levelname)s frontend: %(message)s",
)
log = logging.getLogger("frontend")

PAGES = ["/", "/catalog", "/cart", "/checkout"]


@app.get("/")
def index():
    log.info("serving homepage")
    return "<h1>Demo Shop</h1><p>Frontend is up.</p>"


@app.get("/api/ping")
def ping():
    log.info("ping received")
    return jsonify(service="frontend", status="ok")


def simulated_traffic():
    # Generates a steady stream of logs on its own, so students can see new
    # pods show up in Kibana without needing to click anything by hand.
    while True:
        page = random.choice(PAGES)
        render_ms = random.randint(10, 800)
        if render_ms > 600:
            log.warning("slow render for %s (%dms)", page, render_ms)
        else:
            log.info("user visited %s (%dms)", page, render_ms)
        time.sleep(random.uniform(1, 3))


threading.Thread(target=simulated_traffic, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
