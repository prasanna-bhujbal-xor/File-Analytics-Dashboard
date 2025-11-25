# dashboard/mongo_client.py
from django.conf import settings
from pymongo import MongoClient

def get_mongo_client():
    uri = getattr(settings, "MONGODB_URI", None)
    if uri:
        client = MongoClient(uri)
    else:
        host = settings.MONGODB.get("HOST", "localhost")
        port = settings.MONGODB.get("PORT", 27017)
        user = settings.MONGODB.get("USER", None)
        password = settings.MONGODB.get("PASSWORD", None)
        if user and password:
            mongo_uri = f"mongodb://{user}:{password}@{host}:{port}/{settings.MONGODB.get('DB')}"
            client = MongoClient(mongo_uri)
        else:
            client = MongoClient(host, port)
    return client

def get_files_collection():
    client = get_mongo_client()
    db_name = getattr(settings, "MONGODB_URI", None)
    # If using URI with DB at end, client.get_default_database() returns correct DB
    if getattr(settings, "MONGODB_URI", None):
        db = client.get_default_database()
    else:
        db = client[settings.MONGODB.get("DB", "file_analytics")]
    return db['files']  # collection name "files"
