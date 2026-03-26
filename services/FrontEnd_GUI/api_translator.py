#!/usr/bin/env python3
"""
api_translator.py - FastAPI server that translates REST API calls to gRPC services
This server acts as a bridge between the frontend (REST) and backend gRPC services.
"""

import sys
import os
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, date, time
from contextlib import asynccontextmanager

# Add the generated_python folder to sys.path for gRPC imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../xcode-build/generated_python")))

# FastAPI imports
from fastapi import FastAPI, HTTPException, status, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ConfigDict
import uvicorn

# Import gRPC clients from common/clients
# Since the clients are in common/clients/, we need to add that path
common_clients_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../common/clients"))
sys.path.insert(0, common_clients_path)

# Import the client modules
try:
    from patient_client import PatientManagementClient, Patient, ansi as patient_ansi
    from staff_client import StaffManagementClient, ansi as staff_ansi
    from room_client import RoomManagementClient, Room, Patient as RoomPatient, Staff as RoomStaff, Resource as RoomResource
    from resource_client import ResourceManagementClient
except ImportError as e:
    print(f"Warning: Could not import client modules: {e}")
    print(f"Make sure the common/clients path is correct: {common_clients_path}")
    # Create placeholder classes if imports fail
    class PatientManagementClient:
        def __init__(self, target): pass
    class StaffManagementClient:
        def __init__(self, target): pass
    class RoomManagementClient:
        def __init__(self, target): pass
    class ResourceManagementClient:
        def __init__(self, target): pass
    class Patient: pass
    class Room: pass

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
GRPC_TARGET = os.getenv("GRPC_TARGET", "localhost:50051")
SERVICE_NAME = "api_translator"

# Initialize gRPC clients
patient_client = PatientManagementClient(GRPC_TARGET)
staff_client = StaffManagementClient(GRPC_TARGET)
room_client = RoomManagementClient(GRPC_TARGET)
# resource_client = ResourceManagementClient(GRPC_TARGET)  # Uncomment when implemented


# ============= Pydantic Models for Request/Response =============

# Name Model
class NameModel(BaseModel):
    first: str = Field(..., min_length=1, max_length=100, description="First name")
    middle: str = Field(default="", max_length=100, description="Middle name")
    last: str = Field(..., min_length=1, max_length=100, description="Last name")
    
    model_config = ConfigDict(from_attributes=True)


# Patient Models
class PatientCreate(BaseModel):
    patient_name: NameModel
    sex: str = Field(..., pattern="^(M|F|Other)$", description="Sex (M/F/Other)")
    condition: str = Field(..., max_length=500, description="Patient condition")
    room_type: str = Field(..., description="Room type for admission")
    is_quarantined: bool = Field(default=False, description="Whether patient is quarantined")
    
    model_config = ConfigDict(from_attributes=True)


class PatientUpdate(BaseModel):
    patient_name: Optional[NameModel] = None
    sex: Optional[str] = Field(None, pattern="^(M|F|Other)$")
    condition: Optional[str] = Field(None, max_length=500)
    room_id: Optional[int] = None
    room_type: Optional[str] = None
    is_quarantined: Optional[bool] = None
    
    model_config = ConfigDict(from_attributes=True)


class PatientResponse(BaseModel):
    patient_id: int
    patient_name: NameModel
    sex: str
    condition: str
    room_id: int
    room_type: str
    is_quarantined: bool
    
    model_config = ConfigDict(from_attributes=True)


class PatientTransfer(BaseModel):
    patient_id: int
    old_room_id: int
    new_room_id: int
    room_type: str
    is_quarantined: bool
    
    model_config = ConfigDict(from_attributes=True)


class PatientQuarantine(BaseModel):
    patient_id: int
    quarantine_patient: bool = Field(..., description="True to quarantine, False to lift")
    quarantine_room: bool = Field(False, description="Also quarantine the room")
    
    model_config = ConfigDict(from_attributes=True)


# Staff Models
class StaffCreate(BaseModel):
    staff_name: NameModel
    sex: str = Field(..., pattern="^(M|F|Other)$")
    position: str = Field(..., max_length=100)
    salary: float = Field(..., ge=0)
    clearance: str = Field(..., max_length=50)
    
    model_config = ConfigDict(from_attributes=True)


class StaffUpdate(BaseModel):
    position: Optional[str] = Field(None, max_length=100)
    clearance: Optional[str] = Field(None, max_length=50)
    
    model_config = ConfigDict(from_attributes=True)


class StaffResponse(BaseModel):
    staff_id: int
    staff_name: NameModel
    sex: str
    position: str
    salary: float
    clearance: str
    room: Optional[int] = None
    
    model_config = ConfigDict(from_attributes=True)


class ShiftInfo(BaseModel):
    staff_id: int
    room_id: int
    start: str
    duration_hrs: float


class ScheduleResponse(BaseModel):
    shifts: List[ShiftInfo] = []
    
    model_config = ConfigDict(from_attributes=True)


# Room Models
class RoomResponse(BaseModel):
    room_id: int
    room_type: str
    room_capacity: int
    current_capacity: int
    quarantined: bool
    staff: List[Dict[str, Any]] = []
    patients: List[Dict[str, Any]] = []
    resources: List[Dict[str, Any]] = []
    
    model_config = ConfigDict(from_attributes=True)


class RoomQuarantineRequest(BaseModel):
    room_id: int
    quarantine: bool
    move_patients: bool = Field(False, description="Move patients out of quarantined room")
    
    model_config = ConfigDict(from_attributes=True)


# Resource Models (to be expanded when resource client is implemented)
class ResourceResponse(BaseModel):
    resource_id: int
    resource_type: str
    stock: int
    
    model_config = ConfigDict(from_attributes=True)


# ============= FastAPI Application =============

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown events"""
    logger.info(f"Starting API Translator, connecting to gRPC server at {GRPC_TARGET}")
    
    # Test connection to gRPC services
    try:
        if patient_client.ping(SERVICE_NAME):
            logger.info("Patient Management service is reachable")
        else:
            logger.warning("Patient Management service ping failed")
    except Exception as e:
        logger.error(f"Error pinging Patient Management: {e}")
    
    try:
        if staff_client.ping(SERVICE_NAME):
            logger.info("Staff Management service is reachable")
        else:
            logger.warning("Staff Management service ping failed")
    except Exception as e:
        logger.error(f"Error pinging Staff Management: {e}")
    
    try:
        if room_client.ping(SERVICE_NAME):
            logger.info("Room Management service is reachable")
        else:
            logger.warning("Room Management service ping failed")
    except Exception as e:
        logger.error(f"Error pinging Room Management: {e}")
    
    yield
    
    # Shutdown
    logger.info("Shutting down API Translator")


app = FastAPI(
    title="Hospital Management API Translator",
    description="REST API gateway for Hospital Management gRPC services",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============= Helper Functions =============

def convert_name_to_dto(name: NameModel) -> dict:
    """Convert Pydantic NameModel to dictionary for gRPC"""
    return {
        "first": name.first,
        "middle": name.middle,
        "last": name.last
    }


def convert_patient_to_response(patient: Patient) -> PatientResponse:
    """Convert gRPC Patient model to PatientResponse"""
    return PatientResponse(
        patient_id=patient.patient_id,
        patient_name=NameModel(
            first=patient.first,
            middle=patient.middle,
            last=patient.last
        ),
        sex=patient.sex,
        condition=patient.condition,
        room_id=patient.room_id,
        room_type=patient.room_type,
        is_quarantined=patient.is_quarantined
    )


# ============= Health Check Endpoints =============

@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "grpc_target": GRPC_TARGET}


@app.get("/ping", tags=["Health"])
async def ping():
    """Ping all gRPC services"""
    results = {
        "patient_management": patient_client.ping(SERVICE_NAME),
        "staff_management": staff_client.ping(SERVICE_NAME),
        "room_management": room_client.ping(SERVICE_NAME),
        "resource_management": True  # Placeholder
    }
    return results


# ============= Patient Management Endpoints =============

@app.post("/patients", response_model=PatientResponse, status_code=status.HTTP_201_CREATED, tags=["Patients"])
async def create_patient(patient_data: PatientCreate):
    """
    Admit a new patient to the hospital
    
    - **patient_name**: Patient's full name (first, middle, last)
    - **sex**: Patient's sex (M/F/Other)
    - **condition**: Medical condition description
    - **room_type**: Type of room for admission (e.g., "General", "ICU", "Private")
    - **is_quarantined**: Whether patient needs quarantine
    """
    # Generate a temporary ID (server will assign actual ID)
    # For now, use 0 as placeholder - the gRPC server should generate the ID
    patient = Patient(
        patient_id=0,
        first=patient_data.patient_name.first,
        middle=patient_data.patient_name.middle,
        last=patient_data.patient_name.last,
        sex=patient_data.sex,
        condition=patient_data.condition,
        room_id=0,
        room_type=patient_data.room_type,
        is_quarantined=patient_data.is_quarantined
    )
    
    success = patient_client.admit_patient(
        patient=patient,
        room_type=patient_data.room_type,
        quarantined=patient_data.is_quarantined,
        service_name=SERVICE_NAME
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to admit patient"
        )
    
    # After admission, we would need to retrieve the patient info
    # For now, return a placeholder response
    # In a real implementation, you'd want to get the assigned ID from the response
    
    # This is a workaround - in practice, the admit_patient should return the created patient
    # For now, we'll return a mock response
    return PatientResponse(
        patient_id=0,  # This should be the actual ID
        patient_name=patient_data.patient_name,
        sex=patient_data.sex,
        condition=patient_data.condition,
        room_id=0,
        room_type=patient_data.room_type,
        is_quarantined=patient_data.is_quarantined
    )


@app.get("/patients/{patient_id}", response_model=PatientResponse, tags=["Patients"])
async def get_patient(patient_id: int):
    """Get patient information by ID"""
    patient = patient_client.get_patient_information(patient_id, SERVICE_NAME)
    
    if patient.patient_id == 0 and not patient.first:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patient with ID {patient_id} not found"
        )
    
    return convert_patient_to_response(patient)


@app.put("/patients/{patient_id}", response_model=PatientResponse, tags=["Patients"])
async def update_patient(patient_id: int, patient_data: PatientUpdate):
    """Update patient information"""
    # First get existing patient
    existing = patient_client.get_patient_information(patient_id, SERVICE_NAME)
    
    if existing.patient_id == 0 and not existing.first:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patient with ID {patient_id} not found"
        )
    
    # Update with new data
    if patient_data.patient_name:
        existing.first = patient_data.patient_name.first
        existing.middle = patient_data.patient_name.middle
        existing.last = patient_data.patient_name.last
    if patient_data.sex:
        existing.sex = patient_data.sex
    if patient_data.condition:
        existing.condition = patient_data.condition
    if patient_data.room_id is not None:
        existing.room_id = patient_data.room_id
    if patient_data.room_type:
        existing.room_type = patient_data.room_type
    if patient_data.is_quarantined is not None:
        existing.is_quarantined = patient_data.is_quarantined
    
    success = patient_client.update_patient_information(existing, SERVICE_NAME)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update patient information"
        )
    
    return convert_patient_to_response(existing)


@app.delete("/patients/{patient_id}", tags=["Patients"])
async def discharge_patient(patient_id: int):
    """Discharge a patient from the hospital"""
    # First get patient info
    patient = patient_client.get_patient_information(patient_id, SERVICE_NAME)
    
    if patient.patient_id == 0 and not patient.first:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patient with ID {patient_id} not found"
        )
    
    success = patient_client.discharge_patient(patient, SERVICE_NAME)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to discharge patient"
        )
    
    return {"message": f"Patient {patient_id} discharged successfully"}


@app.post("/patients/transfer", tags=["Patients"])
async def transfer_patient(transfer_data: PatientTransfer):
    """Transfer a patient to a different room"""
    success = patient_client.transfer_patient(
        patient_id=transfer_data.patient_id,
        old_room_id=transfer_data.old_room_id,
        new_room_id=transfer_data.new_room_id,
        room_type=transfer_data.room_type,
        is_quarantined=transfer_data.is_quarantined,
        service_name=SERVICE_NAME
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to transfer patient {transfer_data.patient_id}"
        )
    
    return {"message": f"Patient {transfer_data.patient_id} transferred successfully"}


@app.post("/patients/quarantine", tags=["Patients"])
async def quarantine_patient(quarantine_data: PatientQuarantine):
    """Apply or lift quarantine for a patient"""
    success = patient_client.quarantine_patient(
        patient_id=quarantine_data.patient_id,
        quarantine_patient=quarantine_data.quarantine_patient,
        quarantine_room=quarantine_data.quarantine_room,
        service_name=SERVICE_NAME
    )
    
    if not success:
        action = "quarantine" if quarantine_data.quarantine_patient else "lift quarantine from"
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to {action} patient {quarantine_data.patient_id}"
        )
    
    action = "quarantined" if quarantine_data.quarantine_patient else "quarantine lifted"
    return {"message": f"Patient {quarantine_data.patient_id} {action} successfully"}


# ============= Staff Management Endpoints =============

@app.post("/staff", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED, tags=["Staff"])
async def create_staff(staff_data: StaffCreate):
    """Add a new staff member"""
    success = staff_client.addStaff(
        first=staff_data.staff_name.first,
        middle=staff_data.staff_name.middle,
        last=staff_data.staff_name.last,
        sex=staff_data.sex,
        position=staff_data.position,
        salary=staff_data.salary,
        clearance=staff_data.clearance,
        service_name=SERVICE_NAME
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to add staff member"
        )
    
    return {"message": "Staff member added successfully"}


@app.get("/staff/{staff_id}", response_model=StaffResponse, tags=["Staff"])
async def get_staff(staff_id: int):
    """Get staff information by ID"""
    staff_info = staff_client.getInfo(staff_id, SERVICE_NAME)
    
    if staff_info is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Staff member with ID {staff_id} not found"
        )
    
    # Parse name from the stored string
    name_parts = staff_info.get("name", "").split()
    first = name_parts[0] if name_parts else ""
    last = name_parts[-1] if len(name_parts) > 1 else ""
    middle = " ".join(name_parts[1:-1]) if len(name_parts) > 2 else ""
    
    return StaffResponse(
        staff_id=staff_info["staff_id"],
        staff_name=NameModel(first=first, middle=middle, last=last),
        sex=staff_info["sex"],
        position=staff_info["position"],
        salary=staff_info["salary"],
        clearance=staff_info["clearance"],
        room=staff_info.get("room")
    )


@app.delete("/staff/{staff_id}", tags=["Staff"])
async def delete_staff(staff_id: int):
    """Remove a staff member"""
    success = staff_client.removeStaff(staff_id, SERVICE_NAME)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to remove staff member {staff_id}"
        )
    
    return {"message": f"Staff member {staff_id} removed successfully"}


@app.put("/staff/{staff_id}/position", tags=["Staff"])
async def update_staff_position(staff_id: int, position: str):
    """Update staff member's position"""
    success = staff_client.changePosition(staff_id, position, SERVICE_NAME)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update position for staff {staff_id}"
        )
    
    return {"message": f"Position updated to {position}"}


@app.put("/staff/{staff_id}/clearance", tags=["Staff"])
async def update_staff_clearance(staff_id: int, clearance: str):
    """Update staff member's clearance level"""
    success = staff_client.changeClearance(staff_id, clearance, SERVICE_NAME)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update clearance for staff {staff_id}"
        )
    
    return {"message": f"Clearance updated to {clearance}"}


@app.get("/staff/{staff_id}/schedule/today", response_model=ScheduleResponse, tags=["Staff"])
async def get_today_schedule(staff_id: int):
    """Get today's schedule for a staff member"""
    schedule = staff_client.getTodaysSchedule(staff_id, SERVICE_NAME)
    
    return ScheduleResponse(shifts=schedule.get("shifts", []))


@app.get("/staff/{staff_id}/schedule/tomorrow", response_model=ScheduleResponse, tags=["Staff"])
async def get_tomorrow_schedule(staff_id: int):
    """Get tomorrow's schedule for a staff member"""
    schedule = staff_client.getTomorrowsSchedule(staff_id, SERVICE_NAME)
    
    return ScheduleResponse(shifts=schedule.get("shifts", []))


# ============= Room Management Endpoints =============

@app.get("/rooms/{room_id}", response_model=RoomResponse, tags=["Rooms"])
async def get_room(room_id: int):
    """Get room information by ID"""
    room = room_client.getInfo(room_id, SERVICE_NAME)
    
    if room.room_id != room_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Room with ID {room_id} not found"
        )
    
    return RoomResponse(
        room_id=room.room_id,
        room_type=room.room_type,
        room_capacity=room.room_capacity,
        current_capacity=room.current_capacity,
        quarantined=room.quarantined,
        staff=[
            {"staff_id": s.staff_id, "name": f"{s.first} {s.last}"}
            for s in room.staff
        ],
        patients=[
            {"patient_id": p.patient_id, "name": f"{p.first} {p.last}", "condition": p.condition}
            for p in room.patients
        ],
        resources=[
            {"resource_id": r.resource_id, "type": r.resource_type, "stock": r.stock}
            for r in room.resources
        ]
    )


@app.post("/rooms/quarantine", tags=["Rooms"])
async def quarantine_room(quarantine_data: RoomQuarantineRequest):
    """Apply or lift quarantine for a room"""
    success = room_client.quarantine(
        room_id=quarantine_data.room_id,
        quarantine=quarantine_data.quarantine,
        move_patients=quarantine_data.move_patients,
        service_name=SERVICE_NAME
    )
    
    if not success:
        action = "quarantine" if quarantine_data.quarantine else "lift quarantine from"
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to {action} room {quarantine_data.room_id}"
        )
    
    action = "quarantined" if quarantine_data.quarantine else "quarantine lifted"
    return {"message": f"Room {quarantine_data.room_id} {action} successfully"}


@app.get("/rooms/{room_id}/patients", tags=["Rooms"])
async def get_patients_in_room(room_id: int):
    """Get all patients currently in a room"""
    patients = patient_client.get_patients_in_room(room_id, SERVICE_NAME)
    
    return [
        {
            "patient_id": p.patient_id,
            "name": f"{p.first} {p.last}",
            "condition": p.condition,
            "is_quarantined": p.is_quarantined
        }
        for p in patients
    ]


# ============= Common Service Endpoints =============

@app.post("/services/{service_name}/print", tags=["Services"])
async def print_service(service_name: str):
    """Trigger print operation on a service"""
    # Map service names to appropriate clients
    client_map = {
        "patient": patient_client,
        "staff": staff_client,
        "room": room_client,
    }
    
    client = client_map.get(service_name.lower())
    if not client:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown service: {service_name}"
        )
    
    success = client.print_service(SERVICE_NAME)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to trigger print on {service_name} service"
        )
    
    return {"message": f"Print triggered on {service_name} service"}


@app.post("/services/{service_name}/update", tags=["Services"])
async def update_service(service_name: str):
    """Trigger update operation on a service"""
    client_map = {
        "patient": patient_client,
        "staff": staff_client,
        "room": room_client,
    }
    
    client = client_map.get(service_name.lower())
    if not client:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown service: {service_name}"
        )
    
    success = client.update(SERVICE_NAME)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to trigger update on {service_name} service"
        )
    
    return {"message": f"Update triggered on {service_name} service"}


# ============= Main Entry Point =============

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )