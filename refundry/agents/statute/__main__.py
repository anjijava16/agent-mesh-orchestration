import uvicorn

from refundry.agents.statute.executor import app
from refundry.config import HOST, PORTS

if __name__ == "__main__":
    uvicorn.run(app(), host=HOST, port=PORTS["statute"], log_level="warning")
