"""
Firebase Cloud Firestore REST Endpoints
"""
from fastapi import APIRouter, Query, HTTPException
from typing import List, Dict, Any
from app.firebase_manager import firebase_mgr

router = APIRouter(prefix="/api/firebase", tags=["Firebase"])


@router.get("/status")
def get_firebase_status():
    is_online, err = firebase_mgr.check_cloud_connection()
    return {
        "initialized": firebase_mgr.is_initialized,
        "online": is_online,
        "project_id": firebase_mgr.project_id,
        "last_error": err or firebase_mgr.last_error
    }


@router.get("/measurements", response_model=List[Dict[str, Any]])
def get_firestore_measurements(limit: int = Query(50, ge=1, le=500)):
    if not firebase_mgr.is_initialized:
        raise HTTPException(status_code=503, detail="Firebase Admin SDK is not initialized.")
    return firebase_mgr.get_historical_measurements(limit=limit)


@router.get("/window_reports", response_model=List[Dict[str, Any]])
def get_firestore_window_reports(limit: int = Query(50, ge=1, le=500)):
    if not firebase_mgr.is_initialized:
        raise HTTPException(status_code=503, detail="Firebase Admin SDK is not initialized.")
    return firebase_mgr.get_window_reports(limit=limit)


@router.get("/leak_events", response_model=List[Dict[str, Any]])
def get_firestore_leak_events(limit: int = Query(50, ge=1, le=500)):
    if not firebase_mgr.is_initialized:
        raise HTTPException(status_code=503, detail="Firebase Admin SDK is not initialized.")
    return firebase_mgr.get_leak_events(limit=limit)
