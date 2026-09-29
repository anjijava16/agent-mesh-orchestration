import uvicorn

from refundry.agents.tracer.executor import app
from refundry.config import HOST, PORTS

if __name__ == "__main__":
    uvicorn.run(app(), host=HOST, port=PORTS["tracer"], log_level="warning")
