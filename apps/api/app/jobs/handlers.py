"""Job type → handler map."""

from app.config import Settings
from app.jobs.worker import Handler
from app.providers.registry import Providers
from app.services.account import make_delete_account_handler
from app.services.compare import make_compare_handler
from app.services.ingest import make_ingest_handler
from app.services.review import make_review_handler
from app.services.study import make_flashcards_handler, make_summary_handler


def build_handlers(providers: Providers, settings: Settings) -> dict[str, Handler]:
    return {
        "ingest_paper": make_ingest_handler(providers, settings),
        "build_summary": make_summary_handler(providers),
        "flashcards": make_flashcards_handler(providers),
        "compare": make_compare_handler(providers),
        "lit_review": make_review_handler(providers),
        "delete_account": make_delete_account_handler(providers),
    }
