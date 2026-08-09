from __future__ import annotations

import uvicorn

from edge_agent.config import EdgeSettings


def main() -> None:
    settings = EdgeSettings.from_env()
    uvicorn.run(
        "edge_agent.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
