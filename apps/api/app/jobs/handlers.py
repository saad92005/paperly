"""Job type → handler map. Each phase registers its job types here."""

from app.config import Settings
from app.jobs.worker import Handler
from app.providers.registry import Providers
from app.services.ingest import make_ingest_handler


def build_handlers(providers: Providers, settings: Settings) -> dict[str, Handler]:
    return {
        "ingest_paper": make_ingest_handler(providers, settings),
    }
