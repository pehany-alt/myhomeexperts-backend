from fastapi import FastAPI, APIRouter, HTTPException
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
import uuid
from datetime import datetime, timezone
from google_calendar import create_consultation_meeting, list_upcoming_consultations


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app without a prefix
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")


# Define Models
class StatusCheck(BaseModel):
    model_config = ConfigDict(extra="ignore")  # Ignore MongoDB's _id field
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class StatusCheckCreate(BaseModel):
    client_name: str

class ConsultationRequest(BaseModel):
    name: str
    email: str
    phone: str
    propertyLocation: Optional[str] = None
    projectTimeline: Optional[str] = None
    budgetRange: Optional[str] = None
    preferredStyle: Optional[str] = None
    message: str
    consultationDate: str  # ISO format date string
    consultationTime: Optional[str] = "10:00"  # Time in HH:MM format

class ConsultationResponse(BaseModel):
    success: bool
    message: str
    meet_link: Optional[str] = None
    event_id: Optional[str] = None
    start_time: Optional[str] = None

# Add your routes to the router instead of directly to app
@api_router.get("/")
async def root():
    return {"message": "Hello World"}

@api_router.post("/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate):
    status_dict = input.model_dump()
    status_obj = StatusCheck(**status_dict)
    
    # Convert to dict and serialize datetime to ISO string for MongoDB
    doc = status_obj.model_dump()
    doc['timestamp'] = doc['timestamp'].isoformat()
    
    _ = await db.status_checks.insert_one(doc)
    return status_obj

@api_router.get("/status", response_model=List[StatusCheck])
async def get_status_checks():
    # Exclude MongoDB's _id field from the query results
    status_checks = await db.status_checks.find({}, {"_id": 0}).to_list(1000)
    
    # Convert ISO string timestamps back to datetime objects
    for check in status_checks:
        if isinstance(check['timestamp'], str):
            check['timestamp'] = datetime.fromisoformat(check['timestamp'])
    
    return status_checks

@api_router.post("/consultation", response_model=ConsultationResponse)
async def book_consultation(request: ConsultationRequest):
    """
    Book a consultation and create Google Calendar event with Meet link.
    """
    try:
        # Validate consultation date
        if not request.consultationDate:
            raise HTTPException(status_code=400, detail="Consultation date is required")
        
        # Create Google Calendar event with Meet link
        calendar_result = create_consultation_meeting(
            client_name=request.name,
            client_email=request.email,
            consultation_date_str=request.consultationDate,
            consultation_time_str=request.consultationTime or "10:00",
            duration_minutes=30
        )
        
        if not calendar_result.get('success'):
            raise HTTPException(
                status_code=500, 
                detail=f"Failed to create calendar event: {calendar_result.get('error', 'Unknown error')}"
            )
        
        # Store consultation request in database
        consultation_data = {
            "id": str(uuid.uuid4()),
            "name": request.name,
            "email": request.email,
            "phone": request.phone,
            "propertyLocation": request.propertyLocation,
            "projectTimeline": request.projectTimeline,
            "budgetRange": request.budgetRange,
            "preferredStyle": request.preferredStyle,
            "message": request.message,
            "consultationDate": request.consultationDate,
            "consultationTime": request.consultationTime or "10:00",
            "meetLink": calendar_result.get('meet_link'),
            "calendarEventId": calendar_result.get('event_id'),
            "status": "scheduled",
            "createdAt": datetime.utcnow()
        }
        
        await db.consultations.insert_one(consultation_data)
        
        return ConsultationResponse(
            success=True,
            message=f"Consultation scheduled successfully for {calendar_result.get('start_time')}. Google Meet link has been sent to your email.",
            meet_link=calendar_result.get('meet_link'),
            event_id=calendar_result.get('event_id'),
            start_time=calendar_result.get('start_time')
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error booking consultation: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to book consultation: {str(e)}")

@api_router.get("/consultations")
async def get_upcoming_consultations():
    """
    Get list of upcoming consultations from Google Calendar.
    """
    try:
        result = list_upcoming_consultations(max_results=20)
        
        if not result.get('success'):
            raise HTTPException(status_code=500, detail=result.get('error', 'Failed to fetch consultations'))
        
        return {"success": True, "consultations": result.get('events', [])}
    except Exception as e:
        logger.error(f"Error fetching consultations: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()