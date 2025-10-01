# app.py
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field
import numpy as np
from sklearn.ensemble import IsolationForest
import logging
import asyncio
from typing import List, Optional
import time
import joblib
import os
import shutil
import uvicorn

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize FastAPI application
app = FastAPI(
    title="Verifiable Intelligence Engine Anomaly Detection Core",
    description="Deterministic platform for identifying data anomalies and calculating Empirical Verifiability Scores, compliant with GDPR and eIDAS 2.0 principles.",
    version="1.0.0"
)

MODEL_DIR = "models"
os.makedirs(MODEL_DIR, exist_ok=True)

class DataInput(BaseModel):
    data: List[List[float]] = Field(..., description="List of data samples, where each sample is a list of features.")
    model_id: str = Field("default_model", description="Identifier for the anomaly detection model to use.")
    contamination: float = Field(0.01, ge=0.0, le=0.5, description="Expected proportion of outliers in the data. Used for Isolation Forest training.")

class AnomalyDetectionOutput(BaseModel):
    model_id: str
    anomalies: List[int] = Field(..., description="List of indices of detected anomalous data points (1 for normal, -1 for anomaly).")
    empirical_verifiability_score: float = Field(..., description="A quantifiable score indicating data verifiability (0 to 1, higher is better).")
    processing_time_ms: float = Field(..., description="Time taken for processing in milliseconds.")

class ModelStatus(BaseModel):
    model_id: str
    is_trained: bool
    data_shape: Optional[int] = None

class TrainingData(BaseModel):
    data: List[List[float]] = Field(..., description="Training data samples, where each sample is a list of features.")
    model_id: str = Field("default_model", description="Identifier for the model to train.")
    contamination: float = Field(0.01, ge=0.0, le=0.5, description="Expected proportion of outliers in the data.")

class TrainingResult(BaseModel):
    model_id: str
    status: str
    message: str

def _get_model_path(model_id: str) -> str:
    return os.path.join(MODEL_DIR, f"{model_id}.joblib")

def _train_model_sync(model_id: str, data: np.ndarray, contamination: float) -> IsolationForest:
    logger.info(f"Training new Isolation Forest model '{model_id}' with data shape {data.shape} and contamination {contamination}.")
    model = IsolationForest(contamination=contamination, random_state=42)
    model.fit(data)
    joblib.dump(model, _get_model_path(model_id))
    logger.info(f"Model '{model_id}' trained and saved.")
    return model

async def get_or_train_model(model_id: str, data: np.ndarray, contamination: float) -> IsolationForest:
    model_path = _get_model_path(model_id)
    if os.path.exists(model_path):
        logger.info(f"Loading model '{model_id}' from disk.")
        return joblib.load(model_path)
    else:
        return await asyncio.to_thread(_train_model_sync, model_id, data, contamination)

@app.post("/train-model", response_model=TrainingResult, status_code=status.HTTP_201_CREATED)
async def train_model_endpoint(training_data: TrainingData):
    if not training_data.data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Training data cannot be empty.")
    data_np = np.array(training_data.data)
    if data_np.ndim != 2:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Training data must be a list of lists (2D array).")
    try:
        await get_or_train_model(training_data.model_id, data_np, training_data.contamination)
        return TrainingResult(model_id=training_data.model_id, status="Success", message="Model trained and saved.")
    except Exception as e:
        logger.error(f"Error training model {training_data.model_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to train model: {e}")

@app.post("/detect-anomalies", response_model=AnomalyDetectionOutput, summary="Detects anomalies in input data and provides Verifiability Score.")
async def detect_anomalies_endpoint(input_data: DataInput):
    start_time = time.perf_counter()
    if not input_data.data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Input data cannot be empty.")
    data_np = np.array(input_data.data)
    if data_np.ndim != 2:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Input data must be a list of lists (2D array).")
    try:
        model = await get_or_train_model(input_data.model_id, data_np, input_data.contamination)
        anomaly_predictions = model.predict(data_np).tolist()
        anomaly_scores = model.decision_function(data_np)
        min_score = anomaly_scores.min()
        max_score = anomaly_scores.max()
        if max_score == min_score:
            empirical_verifiability_score = 1.0
        else:
            normalized_scores = (anomaly_scores - min_score) / (max_score - min_score)
            empirical_verifiability_score = float(np.mean(normalized_scores))
        end_time = time.perf_counter()
        processing_time_ms = (end_time - start_time) * 1000
        return AnomalyDetectionOutput(
            model_id=input_data.model_id,
            anomalies=anomaly_predictions,
            empirical_verifiability_score=empirical_verifiability_score,
            processing_time_ms=processing_time_ms
        )
    except Exception as e:
        logger.error(f"Error during anomaly detection: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Anomaly detection failed: {e}")

@app.get("/model-status/{model_id}", response_model=ModelStatus, summary="Get the status of a specific model.")
async def get_model_status_endpoint(model_id: str):
    model_path = _get_model_path(model_id)
    if os.path.exists(model_path):
        try:
            model = joblib.load(model_path)
            return ModelStatus(model_id=model_id, is_trained=True, data_shape=None)
        except Exception as e:
            logger.error(f"Error loading model '{model_id}': {e}")
            return ModelStatus(model_id=model_id, is_trained=False, data_shape=None)
    return ModelStatus(model_id=model_id, is_trained=False, data_shape=None)

@app.get("/health", status_code=status.HTTP_200_OK, summary="Health check endpoint.")
async def health_check():
    return {"status": "operational", "timestamp": time.time()}

if __name__ == "__main__":
    if os.path.exists(MODEL_DIR):
        shutil.rmtree(MODEL_DIR)
        os.makedirs(MODEL_DIR, exist_ok=True)
    uvicorn.run(app, host="0.0.0.0", port=8000)
