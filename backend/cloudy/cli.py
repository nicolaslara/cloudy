import argparse
from datetime import date

import uvicorn

from cloudy.config import get_settings


def main() -> None:
    parser = argparse.ArgumentParser(prog="cloudy")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve = subparsers.add_parser("serve", help="run the API server")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=get_settings().api_port)
    serve.add_argument("--reload", action="store_true")

    subparsers.add_parser(
        "migrate",
        help="apply pending Alembic migrations (upgrade head)",
    )
    subparsers.add_parser(
        "stamp",
        help="mark DB at migration head without running DDL (one-time for create_all DBs)",
    )

    subparsers.add_parser(
        "create-db",
        help="deprecated alias for migrate",
    )

    ingest = subparsers.add_parser(
        "ingest", help="ingest one source for a date or range (idempotent)"
    )
    ingest.add_argument("source", choices=["lightning", "stations", "cloud"])
    ingest.add_argument("--date", type=date.fromisoformat, help="one day (YYYY-MM-DD)")
    ingest.add_argument("--from", dest="start", type=date.fromisoformat)
    ingest.add_argument("--to", dest="end", type=date.fromisoformat)
    ingest.add_argument("--station", type=int, help="metobs station id (cloud ingest)")
    ingest.add_argument(
        "--all-active",
        action="store_true",
        help="ingest cloud for every active station",
    )
    ingest.add_argument(
        "--period",
        choices=["corrected-archive", "latest-months"],
        default="corrected-archive",
        help="metobs period (cloud ingest only)",
    )

    subparsers.add_parser(
        "backtest",
        help="evaluate the weekly outlook across all stations; write the static benchmark to disk",
    )
    production_ingest = subparsers.add_parser(
        "ingest-production",
        help="run the production smoke, full, or incremental data refresh workflow",
    )
    production_ingest.add_argument(
        "mode",
        choices=["smoke", "full", "incremental"],
        nargs="?",
        default="full",
    )

    args = parser.parse_args()
    if args.command in {"migrate", "create-db"}:
        from cloudy.db.migrate import upgrade_head

        upgrade_head()
    elif args.command == "stamp":
        from cloudy.db.migrate import stamp_head

        stamp_head()
    elif args.command == "ingest":
        run_ingest(parser, args)
    elif args.command == "backtest":
        run_backtest()
    elif args.command == "ingest-production":
        from cloudy.production_ingest import run

        run(args.mode)
    elif args.command == "serve":
        uvicorn.run(
            "cloudy.api:create_app",
            factory=True,
            host=args.host,
            port=args.port,
            reload=args.reload,
            log_level=get_settings().log_level.lower(),
        )


def run_backtest() -> None:
    import json
    from pathlib import Path

    from cloudy.db.session import get_engine
    from cloudy.logging import configure_logging
    from cloudy.predictions import evaluate

    configure_logging(get_settings().log_level)
    engine = get_engine()
    artifact = evaluate.evaluate(engine)
    path = Path(get_settings().predictions_scorecard_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    print(f"wrote weekly-outlook benchmark ({artifact['n_stations']} stations) to {path}")


def run_ingest(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    from cloudy.db.session import get_engine
    from cloudy.ingest import lightning
    from cloudy.logging import configure_logging

    configure_logging(get_settings().log_level)
    if args.source == "stations":
        from cloudy.ingest import stations

        print(f"{stations.ingest(get_engine())} stations upserted")
        return
    if args.source == "cloud":
        from cloudy.ingest import cloud as cloud_ingest

        period = args.period
        if args.all_active:
            cloud_results = cloud_ingest.ingest_all_active(get_engine(), period=period)
            print(f"{sum(r.rows for r in cloud_results)} hours over {len(cloud_results)} stations")
        elif args.station is not None:
            result = cloud_ingest.ingest_station(get_engine(), args.station, period=period)
            print(f"{result.rows} hours for station {result.station_id}")
        else:
            parser.error("cloud ingest needs --station or --all-active")
        return
    if args.source != "lightning":
        parser.error(f"unknown ingest source: {args.source}")
    if args.date:
        start = end = args.date
    elif args.start and args.end:
        start, end = args.start, args.end
    else:
        parser.error("ingest needs --date or both --from and --to")
    results = lightning.ingest_range(get_engine(), start, end)
    print(f"{sum(r.rows for r in results)} events over {len(results)} days")
