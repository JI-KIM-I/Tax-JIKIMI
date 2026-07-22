from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from dotenv import load_dotenv
from pymongo import ASCENDING, DESCENDING, MongoClient

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI")
MONGODB_DB = os.getenv("MONGODB_DB", "TAX-JIKIMI")

_client: MongoClient | None = None


def get_mongo_client() -> MongoClient:
    global _client

    if not MONGODB_URI:
        raise RuntimeError("MONGODB_URI가 설정되지 않았습니다. backend/.env를 확인하세요.")

    if _client is None:
        _client = MongoClient(MONGODB_URI)

    return _client


def get_database():
    return get_mongo_client()[MONGODB_DB]


class _MongoCollectionProxy:
    """환경변수 기반으로 MongoDB 컬렉션을 늦게 연결하는 프록시."""

    def __init__(self, collection_name: str):
        self.collection_name = collection_name

    def _collection(self):
        return get_database()[self.collection_name]

    def __getattr__(self, name: str):
        return getattr(self._collection(), name)


users = _MongoCollectionProxy("users")
user_profiles = _MongoCollectionProxy("user_profiles")
diagnosis_records = _MongoCollectionProxy("diagnosis_records")
reports = _MongoCollectionProxy("reports")
chat_messages = _MongoCollectionProxy("chat_messages")


def init_db_indexes() -> None:
    users.create_index([("email", ASCENDING)], unique=True)
    users.create_index([("nickname", ASCENDING)], unique=True, sparse=True)

    user_profiles.create_index([("user_id", ASCENDING)], unique=True)

    diagnosis_records.create_index(
        [("user_id", ASCENDING), ("created_at", DESCENDING)]
    )
    reports.create_index(
        [("user_id", ASCENDING), ("created_at", DESCENDING)]
    )
    chat_messages.create_index(
        [("user_id", ASCENDING), ("created_at", DESCENDING)]
    )


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def serialize_doc(doc: dict[str, Any] | None):
    if doc is None:
        return None

    result = {}

    for key, value in doc.items():
        if isinstance(value, ObjectId):
            result[key] = str(value)
        elif isinstance(value, datetime):
            result[key] = value.isoformat()
        elif isinstance(value, list):
            result[key] = [
                serialize_doc(v) if isinstance(v, dict) else v for v in value
            ]
        elif isinstance(value, dict):
            result[key] = serialize_doc(value)
        else:
            result[key] = value

    return result
