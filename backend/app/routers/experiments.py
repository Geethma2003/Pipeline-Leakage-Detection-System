"""
Experimental Analysis REST Endpoints
"""
import io
import pandas as pd
from fastapi import APIRouter, UploadFile, File, HTTPException
from typing import List, Dict, Any
from app.config import BASE_DIR
from app.analysis import process_default_experiments, analyze_csv_dataframe
from app.models import ExperimentAnalysisResponse, ExperimentMetricsModel

router = APIRouter(prefix="/api/experiments", tags=["Experiments"])


@router.get("/default", response_model=ExperimentAnalysisResponse)
def get_default_experiments():
    return process_default_experiments(str(BASE_DIR))


@router.post("/upload", response_model=ExperimentMetricsModel)
async def upload_experiment_csv(file: UploadFile = File(...)):
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported.")
    try:
        content = await file.read()
        df = pd.read_csv(io.BytesIO(content))
        label = file.filename.replace(".csv", "").replace("_", " ").title()
        metrics = analyze_csv_dataframe(df, label=label, file_name=file.filename, is_simulated=False)
        return metrics
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse uploaded CSV file: {e}")
