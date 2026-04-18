from db import ensure_indexes, ensure_search_indexes, get_database


def bootstrap():
    db = get_database()
    ensure_indexes()
    ensure_search_indexes()
    print(f"MongoDB bootstrap completed for database: {db.name}")
    print("Collections:", sorted(db.list_collection_names()))


if __name__ == "__main__":
    bootstrap()
