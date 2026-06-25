"""Mongo connection config — supports both MONGO_* and MONGODB_* env names.

The deployment .env uses the MONGODB_* schema (MONGODB_URI / MONGODB_USERNAME
/ MONGODB_PASSWORD / MONGODB_DB_NAME). The historical MONGO_* names still
work. `_env_file=None` isolates each case from the repo .env.
"""

from urllib.parse import quote_plus

from app.core.config import Settings


def test_mongodb_uri_alias_is_honored(monkeypatch):
    # conftest seeds MONGO_URI in the env; clear it so MONGODB_URI is the
    # only URI present (MONGO_URI would otherwise win by alias precedence).
    monkeypatch.delenv("MONGO_URI", raising=False)
    monkeypatch.setenv("MONGODB_URI", "mongodb+srv://u:p@c.mongodb.net/anveksha")
    s = Settings(_env_file=None)
    assert s.mongo_connection_uri == "mongodb+srv://u:p@c.mongodb.net/anveksha"


def test_legacy_mongo_uri_still_honored(monkeypatch):
    monkeypatch.delenv("MONGODB_URI", raising=False)
    monkeypatch.setenv("MONGO_URI", "mongodb://legacy:27017/anveksha")
    s = Settings(_env_file=None)
    assert s.mongo_connection_uri == "mongodb://legacy:27017/anveksha"


def test_mongodb_component_aliases_build_uri(monkeypatch):
    for k in ("MONGO_URI", "MONGODB_URI"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("MONGODB_USERNAME", "rajeshrudravarjula")
    monkeypatch.setenv("MONGODB_PASSWORD", "p@ss:w/rd")
    monkeypatch.setenv("MONGODB_DB_NAME", "anveksha")
    monkeypatch.setenv("MONGO_HOST", "mongo")
    s = Settings(_env_file=None)

    assert s.MONGO_USERNAME == "rajeshrudravarjula"
    assert s.MONGO_DATABASE == "anveksha"
    uri = s.mongo_connection_uri
    # Password is URL-encoded so reserved chars don't corrupt the URI.
    assert quote_plus("p@ss:w/rd") in uri
    assert "rajeshrudravarjula" in uri and "/anveksha" in uri
