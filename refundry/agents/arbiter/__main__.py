import uvicorn

from refundry.agents.arbiter.executor import app
from refundry.config import HOST, PORTS

if __name__ == "__main__":
    uvicorn.run(app(), host=HOST, port=PORTS["arbiter"], log_level="warning")
