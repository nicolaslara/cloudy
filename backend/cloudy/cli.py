import argparse

import uvicorn
from sqlmodel import SQLModel

from cloudy.config import get_settings


def main() -> None:
    parser = argparse.ArgumentParser(prog="cloudy")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve = subparsers.add_parser("serve", help="run the API server")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=get_settings().api_port)
    serve.add_argument("--reload", action="store_true")

    subparsers.add_parser(
        "create-db",
        help="create all tables (no migrations until the schema stabilizes; "
        "drop the dev db to reset)",
    )

    args = parser.parse_args()
    if args.command == "create-db":
        from cloudy.db import models, session  # noqa: F401  (register tables)

        SQLModel.metadata.create_all(session.get_engine())
    elif args.command == "serve":
        uvicorn.run(
            "cloudy.api:create_app",
            factory=True,
            host=args.host,
            port=args.port,
            reload=args.reload,
            log_level=get_settings().log_level.lower(),
        )
