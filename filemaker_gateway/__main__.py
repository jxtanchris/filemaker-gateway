"""Entry point for `python -m filemaker_gateway`."""

import uvicorn
from filemaker_gateway.main import create_app
from filemaker_gateway.config.loader import load_config


def main() -> None:
    config = load_config()
    app = create_app(config)
    uvicorn.run(
        app,
        host=config.gateway.host,
        port=config.gateway.port,
        log_level=config.gateway.log_level.lower(),
    )


if __name__ == "__main__":
    main()
