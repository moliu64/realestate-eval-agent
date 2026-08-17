from app.config import load_config
import uvicorn


def main() -> None:
    config = load_config()
    uvicorn.run("app.server:app", host=config.host, port=config.port)


if __name__ == "__main__":
    main()
