import asyncio
import os
import sqlite3
import threading
from typing import Any

from config import MONGO_URI
from database import create_mongo_client, get_stats_collection


class StatsStore:
    def __init__(self, path: str = "data/user_stats.db"):
        self.mongo_client = None
        self.collection = None
        self.use_mongo = bool(MONGO_URI)

        if self.use_mongo:
            try:
                self.mongo_client = create_mongo_client()
                self.collection = get_stats_collection(self.mongo_client)
                print("[INFO] MongoDB configurado usando URI de ambiente o valor por defecto.")
            except Exception as exc:
                print(f"[WARN] No se pudo inicializar MongoDB; usando SQLite en su lugar. {exc}")
                self.use_mongo = False

        self.path = os.path.abspath(path)
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._lock = threading.Lock()
        self._ensure_table()

    def _ensure_table(self) -> None:
        with self._lock:
            conn = sqlite3.connect(self.path)
            try:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_stats (
                        _id TEXT PRIMARY KEY,
                        axp REAL NOT NULL,
                        exp REAL NOT NULL,
                        messages INTEGER NOT NULL,
                        status TEXT NOT NULL
                    )
                    """
                )
                conn.commit()
            finally:
                conn.close()

    def _disable_mongo(self, exc: Exception) -> None:
        print(f"[WARN] MongoDB deshabilitado: {exc}")
        self.use_mongo = False
        if self.mongo_client is not None:
            try:
                self.mongo_client.close()
            except Exception:
                pass
            self.mongo_client = None
            self.collection = None

    def _get_sync(self, user_id: str) -> dict[str, Any]:
        with self._lock:
            conn = sqlite3.connect(self.path)
            try:
                cur = conn.execute(
                    "SELECT _id, axp, exp, messages, status FROM user_stats WHERE _id = ?",
                    (user_id,),
                )
                row = cur.fetchone()
                if row is None:
                    return {"_id": user_id, "axp": 0.0, "exp": 0.0, "messages": 0, "status": "Operativo"}
                return {
                    "_id": row[0],
                    "axp": float(row[1]),
                    "exp": float(row[2]),
                    "messages": int(row[3]),
                    "status": row[4],
                }
            finally:
                conn.close()

    def _upsert_sync(self, stats: dict[str, Any]) -> None:
        with self._lock:
            conn = sqlite3.connect(self.path)
            try:
                conn.execute(
                    """
                    INSERT INTO user_stats(_id, axp, exp, messages, status)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(_id) DO UPDATE SET
                        axp=excluded.axp,
                        exp=excluded.exp,
                        messages=excluded.messages,
                        status=excluded.status
                    """,
                    (
                        stats["_id"],
                        float(stats.get("axp", 0.0)),
                        float(stats.get("exp", 0.0)),
                        int(stats.get("messages", 0)),
                        stats.get("status", "Operativo"),
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    async def get_user_stats(self, user_id: str) -> dict[str, Any]:
        user_id = str(user_id)
        if self.use_mongo and self.collection is not None:
            try:
                document = await self.collection.find_one({"_id": user_id})
                if document is None:
                    document = {"_id": user_id, "axp": 0.0, "exp": 0.0, "messages": 0, "status": "Operativo"}
                    await self.collection.insert_one(document)
                document.setdefault("axp", 0.0)
                document.setdefault("exp", 0.0)
                document.setdefault("messages", 0)
                document.setdefault("status", "Operativo")
                return document
            except Exception as exc:
                self._disable_mongo(exc)

        return await asyncio.to_thread(self._get_sync, user_id)

    async def update_user_stats(self, user_id: str, updates: dict[str, Any]) -> None:
        user_id = str(user_id)
        if self.use_mongo and self.collection is not None:
            try:
                default = {"_id": user_id, "axp": 0.0, "exp": 0.0, "messages": 0, "status": "Operativo"}
                update_data = {"$set": updates, "$setOnInsert": default}
                await self.collection.update_one({"_id": user_id}, update_data, upsert=True)
                return
            except Exception as exc:
                self._disable_mongo(exc)

        stats = await self.get_user_stats(user_id)
        stats.update(updates)
        await asyncio.to_thread(self._upsert_sync, stats)

    async def verify_mongo(self) -> bool:
        if not self.use_mongo or self.mongo_client is None:
            return False
        try:
            await self.mongo_client.admin.command("ping")
            return True
        except Exception as exc:
            self._disable_mongo(exc)
            return False

    async def add_axp(self, user_id: str, amount: float) -> None:
        stats = await self.get_user_stats(user_id)
        await self.update_user_stats(user_id, {"axp": float(stats.get("axp", 0.0)) + float(amount)})

    async def remove_axp(self, user_id: str, amount: float) -> None:
        stats = await self.get_user_stats(user_id)
        new_value = max(0.0, float(stats.get("axp", 0.0)) - float(amount))
        await self.update_user_stats(user_id, {"axp": new_value})

    async def add_exp(self, user_id: str, amount: float) -> None:
        stats = await self.get_user_stats(user_id)
        await self.update_user_stats(user_id, {"exp": float(stats.get("exp", 0.0)) + float(amount)})

    async def remove_exp(self, user_id: str, amount: float) -> None:
        stats = await self.get_user_stats(user_id)
        new_value = max(0.0, float(stats.get("exp", 0.0)) - float(amount))
        await self.update_user_stats(user_id, {"exp": new_value})

    async def set_axp(self, user_id: str, amount: float) -> None:
        await self.update_user_stats(user_id, {"axp": float(amount)})

    async def set_exp(self, user_id: str, amount: float) -> None:
        await self.update_user_stats(user_id, {"exp": float(amount)})

    async def set_status(self, user_id: str, status: str) -> None:
        await self.update_user_stats(user_id, {"status": status})


stats_store = StatsStore()
