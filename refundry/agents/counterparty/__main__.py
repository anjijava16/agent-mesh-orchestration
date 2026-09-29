import uvicorn

from refundry.agents.counterparty.executor import app
from refundry.config import HOST, PORTS

if __name__ == "__main__":
    uvicorn.run(app(), host=HOST, port=PORTS["counterparty"], log_level="warning")
