import uvicorn

from app.config import get_settings
from app.main import app


def main():
    settings = get_settings()
    uvicorn.run(
        app,
        host=settings["host"],
        port=settings["port"],
        log_level="info",
    )


if __name__ == "__main__":
    main()
