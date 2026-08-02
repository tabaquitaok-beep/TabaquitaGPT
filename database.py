from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGO_URI, MONGO_DB_NAME, STATS_COLLECTION_NAME


def create_mongo_client() -> AsyncIOMotorClient:
    return AsyncIOMotorClient(
        MONGO_URI,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
    )


def get_stats_collection(client: AsyncIOMotorClient):
    return client[MONGO_DB_NAME][STATS_COLLECTION_NAME]
