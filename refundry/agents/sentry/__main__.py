import uvicorn

from refundry.agents.sentry.executor import app
from refundry.config import HOST, PORTS

if __name__ == "__main__":
    uvicorn.run(app(), host=HOST, port=PORTS["sentry"], log_level="warning")
