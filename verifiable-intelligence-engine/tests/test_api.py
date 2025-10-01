import pytest
import httpx
import asyncio
import os
import time

BASE_URL = "http://127.0.0.1:8000"

@pytest.fixture(scope="session", autouse=True)
def start_api_server():
    print("\nPlease ensure the FastAPI server is running at http://127.0.0.1:8000 before running tests.")
    yield

@pytest.mark.asyncio
async def test_health_endpoint():
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "operational"

@pytest.mark.asyncio
async def test_train_model_endpoint():
    model_id = f"test_model_{int(time.time())}"
    data = [[i * 1.0, i * 2.0] for i in range(100)]
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        response = await client.post("/train-model", json={"data": data, "model_id": model_id, "contamination": 0.01})
        assert response.status_code == 201
        assert response.json()["status"] == "Success"
        assert response.json()["model_id"] == model_id

@pytest.mark.asyncio
async def test_detect_anomalies_endpoint_with_new_model():
    model_id = f"test_detection_model_{int(time.time())}"
    train_data = [[1.0, 1.0], [1.1, 1.1], [1.2, 1.2], [10.0, 10.0]]
    detect_data = [[1.15, 1.15], [10.5, 10.5], [1.0, 1.0]]
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        train_response = await client.post("/train-model", json={"data": train_data, "model_id": model_id, "contamination": 0.25})
        assert train_response.status_code == 201
        detect_response = await client.post("/detect-anomalies", json={"data": detect_data, "model_id": model_id})
        assert detect_response.status_code == 200
        result = detect_response.json()
        assert result["model_id"] == model_id
        assert result["anomalies"] == [1, -1, 1]
        assert 0.0 <= result["empirical_verifiability_score"] <= 1.0
        assert result["processing_time_ms"] > 0

@pytest.mark.asyncio
async def test_detect_anomalies_endpoint_empty_data():
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        response = await client.post("/detect-anomalies", json={"data": []})
        assert response.status_code == 400
        assert "Input data cannot be empty" in response.json()["detail"]

@pytest.mark.asyncio
async def test_detect_anomalies_endpoint_invalid_data_shape():
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        response = await client.post("/detect-anomalies", json={"data": [1, 2, 3]})
        assert response.status_code == 422
        assert any("list_type" in err.get("type", "") for err in response.json().get("detail", []))

@pytest.mark.asyncio
async def test_model_status_endpoint():
    model_id = f"status_model_{int(time.time())}"
    data = [[1.0, 2.0]]
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        await client.post("/train-model", json={"data": data, "model_id": model_id, "contamination": 0.01})
        response = await client.get(f"/model-status/{model_id}")
        assert response.status_code == 200
        status_data = response.json()
        assert status_data["model_id"] == model_id
        assert status_data["is_trained"] == True
        response = await client.get("/model-status/non_existent_model")
        assert response.status_code == 200
        status_data = response.json()
        assert status_data["model_id"] == "non_existent_model"
        assert status_data["is_trained"] == False
