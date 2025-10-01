from locust import HttpUser, task, between

class VerifiableIntelligenceEngineUser(HttpUser):
    wait_time = between(1, 3)

    @task(2)
    def health_check(self):
        self.client.get("/health")

    @task(3)
    def train_model(self):
        payload = {
            "data": [[1.0, 2.0], [1.1, 2.1], [100.0, 200.0], [1.2, 2.2]],
            "model_id": "load_test_model",
            "contamination": 0.05
        }
        self.client.post("/train-model", json=payload)

    @task(5)
    def detect_anomalies(self):
        payload = {
            "data": [[1.5, 2.5], [105.0, 210.0], [0.9, 1.9]],
            "model_id": "load_test_model"
        }
        self.client.post("/detect-anomalies", json=payload)
