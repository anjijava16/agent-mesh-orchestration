import uvicorn

from refundry.agents.treasury.executor import app
from refundry.config import HOST, PORTS

if __name__ == "__main__":
    uvicorn.run(app(), host=HOST, port=PORTS["treasury"], log_level="warning")
