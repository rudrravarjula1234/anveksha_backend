import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_ok_when_mongo_up(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["mongo"] == "up"
    assert body["service"] == "anveksha-backend"
