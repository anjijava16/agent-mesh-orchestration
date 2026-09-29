import uvicorn

from refundry.agents.witness.executor import app
from refundry.config import HOST, PORTS

if __name__ == "__main__":
    uvicorn.run(app(), host=HOST, port=PORTS["witness"], log_level="warning")
