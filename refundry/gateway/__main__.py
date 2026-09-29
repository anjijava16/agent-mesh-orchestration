import uvicorn

from refundry.config import HOST, PORTS
from refundry.gateway.app import build

if __name__ == "__main__":
    uvicorn.run(build(), host=HOST, port=PORTS["gateway"], log_level="info")
