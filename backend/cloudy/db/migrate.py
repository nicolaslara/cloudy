"""Alembic migration helpers (upgrade head, stamp for create_all bootstrap)."""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config

from alembic import command


def _alembic_config() -> Config:
    ini = Path(__file__).resolve().parents[2] / "alembic.ini"
    return Config(str(ini))


def upgrade(revision: str = "head") -> None:
    command.upgrade(_alembic_config(), revision)


def upgrade_head() -> None:
    upgrade("head")


def stamp_head() -> None:
    command.stamp(_alembic_config(), "head")
