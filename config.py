import os
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN no está configurado en .env o en el entorno")

DEFAULT_MONGO_URI = "mongodb+srv://tabaquitaok_db_user:F8MA9SEK4F5NJATz@cluster0.qoxx5jn.mongodb.net/?appName=Cluster0"
MONGO_URI = os.getenv("MONGO_URI") or os.getenv("MONGODB_URI") or os.getenv("DATABASE_URL") or DEFAULT_MONGO_URI


def _derive_mongo_db_name(uri: str | None) -> str | None:
    if not uri:
        return None
    try:
        parsed = urlparse(uri)
        if parsed.path:
            name = parsed.path.lstrip("/")
            return name if name else None
    except Exception:
        pass
    return None

MONGO_DB_NAME = os.getenv("MONGO_DB_NAME") or _derive_mongo_db_name(MONGO_URI) or "TabaquitaGPT"
STATS_COLLECTION_NAME = "user_stats"

OWNER_ID = int(os.getenv("OWNER_ID") or 742882682190561343)
STATUS_CHANNEL_ID = int(os.getenv("STATUS_CHANNEL_ID") or 1510791864566022154)

HIGH_COMMAND_ROLE_ID = int(os.getenv("HIGH_COMMAND_ROLE_ID") or 1496612684345512119)
HIGH_RANK_ROLE_ID = int(os.getenv("HIGH_RANK_ROLE_ID") or 1495961100053778434)
MIDDLE_RANK_ROLE_ID = int(os.getenv("MIDDLE_RANK_ROLE_ID") or 1495959303113412750)
LOW_RANK_ROLE_ID = int(os.getenv("LOW_RANK_ROLE_ID") or 1494162106725961849)
MIEMBRO_EXTERNO_ROLE_ID = int(os.getenv("MIEMBRO_EXTERNO_ROLE_ID") or 1516093644720046150)
BOT_ROLE_ID = int(os.getenv("BOT_ROLE_ID") or 1492155946842198086)
WAIT_ROLE_ID = int(os.getenv("WAIT_ROLE_ID") or 1516095262903242831)

ROLE_LEVELS = {
    WAIT_ROLE_ID: 0,
    BOT_ROLE_ID: 1,
    MIEMBRO_EXTERNO_ROLE_ID: 2,
    LOW_RANK_ROLE_ID: 3,
    MIDDLE_RANK_ROLE_ID: 4,
    HIGH_RANK_ROLE_ID: 5,
    HIGH_COMMAND_ROLE_ID: 6,
}

PREFIXES = ["!k ", "!k"]
PORT = int(os.getenv("PORT") or 10000)
