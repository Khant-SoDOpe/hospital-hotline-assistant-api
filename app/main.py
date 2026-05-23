from contextlib import asynccontextmanager
from uuid import UUID
import asyncpg
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.config import settings
from app.database import create_pool, get_connection, record_to_dict, records_to_dicts
from app.schemas import (
    ConversationSummaryOut,
    DepartmentOut,
    DepartmentRecommendationCreate,
    EmergencyEventCreate,
    EmergencyTriggerOut,
    MessageCreate,
    MessageOut,
    RoutingRuleOut,
    SessionCreate,
    SessionOut,
    SessionUpdate,
    SeverityAssessmentCreate,
    SymptomEntryCreate,
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db_pool = await create_pool()
    try:
        yield
    finally:
        await app.state.db_pool.close()

app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(asyncpg.ForeignKeyViolationError)
async def foreign_key_violation_handler(request: Request, exc: asyncpg.ForeignKeyViolationError):
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": "Referenced record does not exist. Check session_id, message_id, assessment_id, department_id, or trigger_id."},
    )

@app.exception_handler(asyncpg.UniqueViolationError)
async def unique_violation_handler(request: Request, exc: asyncpg.UniqueViolationError):
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": "Record already exists."},
    )

@app.get("/")
async def root() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "status": "running",
        "docs": "/docs",
    }

@app.get("/health")
async def health(connection: asyncpg.Connection = Depends(get_connection)) -> dict[str, str]:
    await connection.fetchval("SELECT 1")
    return {"status": "ok", "environment": settings.environment}

@app.post("/sessions", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
async def create_session(payload: SessionCreate, connection: asyncpg.Connection = Depends(get_connection)):
    record = await connection.fetchrow(
        """
        INSERT INTO sessions (language, user_agent, ip_hash, metadata)
        VALUES ($1, $2, $3, $4::jsonb)
        RETURNING *
        """,
        payload.language,
        payload.user_agent,
        payload.ip_hash,
        payload.metadata,
    )
    return record_to_dict(record)

@app.get("/sessions/{session_id}", response_model=SessionOut)
async def get_session(session_id: UUID, connection: asyncpg.Connection = Depends(get_connection)):
    record = await connection.fetchrow("SELECT * FROM sessions WHERE id = $1", session_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return record_to_dict(record)

@app.patch("/sessions/{session_id}", response_model=SessionOut)
async def update_session(session_id: UUID, payload: SessionUpdate, connection: asyncpg.Connection = Depends(get_connection)):
    ended_sql = "NOW()" if payload.status in {"completed", "reset", "escalated"} else "ended_at"
    record = await connection.fetchrow(
        f"""
        UPDATE sessions
        SET status = $2, ended_at = {ended_sql}
        WHERE id = $1
        RETURNING *
        """,
        session_id,
        payload.status,
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return record_to_dict(record)

@app.post("/sessions/{session_id}/messages", response_model=MessageOut, status_code=status.HTTP_201_CREATED)
async def create_message(session_id: UUID, payload: MessageCreate, connection: asyncpg.Connection = Depends(get_connection)):
    record = await connection.fetchrow(
        """
        INSERT INTO messages (
            session_id, role, input_mode, content, audio_url, transcript_confidence,
            model_name, response_latency_ms, metadata
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb)
        RETURNING *
        """,
        session_id,
        payload.role,
        payload.input_mode,
        payload.content,
        payload.audio_url,
        payload.transcript_confidence,
        payload.model_name,
        payload.response_latency_ms,
        payload.metadata,
    )
    return record_to_dict(record)

@app.get("/sessions/{session_id}/messages", response_model=list[MessageOut])
async def list_messages(session_id: UUID, connection: asyncpg.Connection = Depends(get_connection)):
    records = await connection.fetch(
        "SELECT * FROM messages WHERE session_id = $1 ORDER BY created_at ASC",
        session_id,
    )
    return records_to_dicts(records)

@app.post("/sessions/{session_id}/symptoms", status_code=status.HTTP_201_CREATED)
async def create_symptom_entry(session_id: UUID, payload: SymptomEntryCreate, connection: asyncpg.Connection = Depends(get_connection)):
    record = await connection.fetchrow(
        """
        INSERT INTO symptom_entries (
            session_id, message_id, raw_text, normalized_symptoms,
            body_location, duration_text, pain_score
        )
        VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7)
        RETURNING *
        """,
        session_id,
        payload.message_id,
        payload.raw_text,
        payload.normalized_symptoms,
        payload.body_location,
        payload.duration_text,
        payload.pain_score,
    )
    return record_to_dict(record)

@app.post("/sessions/{session_id}/severity-assessments", status_code=status.HTTP_201_CREATED)
async def create_severity_assessment(
    session_id: UUID,
    payload: SeverityAssessmentCreate,
    connection: asyncpg.Connection = Depends(get_connection),
    ):
    record = await connection.fetchrow(
        """
        INSERT INTO severity_assessments (
            session_id, source_message_id, severity, confidence, explanation, detected_triggers
        )
        VALUES ($1, $2, $3, $4, $5, $6::jsonb)
        RETURNING *
        """,
        session_id,
        payload.source_message_id,
        payload.severity,
        payload.confidence,
        payload.explanation,
        payload.detected_triggers,
    )
    return record_to_dict(record)


@app.get("/departments", response_model=list[DepartmentOut])
async def list_departments(connection: asyncpg.Connection = Depends(get_connection)):
    records = await connection.fetch(
        "SELECT * FROM departments WHERE is_active = TRUE ORDER BY name_en ASC"
    )
    return records_to_dicts(records)

@app.get("/routing-rules", response_model=list[RoutingRuleOut])
async def list_routing_rules(connection: asyncpg.Connection = Depends(get_connection)):
    records = await connection.fetch(
        "SELECT * FROM routing_rules WHERE is_active = TRUE ORDER BY priority ASC, rule_name ASC"
    )
    return records_to_dicts(records)

@app.get("/emergency-triggers", response_model=list[EmergencyTriggerOut])
async def list_emergency_triggers(connection: asyncpg.Connection = Depends(get_connection)):
    records = await connection.fetch(
        "SELECT * FROM emergency_triggers WHERE is_active = TRUE ORDER BY priority ASC, trigger_name ASC"
    )
    return records_to_dicts(records)

@app.post("/sessions/{session_id}/department-recommendations", status_code=status.HTTP_201_CREATED)
async def create_department_recommendation(
    session_id: UUID,
    payload: DepartmentRecommendationCreate,
    connection: asyncpg.Connection = Depends(get_connection),
):
    record = await connection.fetchrow(
        """
        INSERT INTO department_recommendations (
            session_id, assessment_id, department_id, confidence, reason
        )
        VALUES ($1, $2, $3, $4, $5)
        RETURNING *
        """,
        session_id,
        payload.assessment_id,
        payload.department_id,
        payload.confidence,
        payload.reason,
    )
    return record_to_dict(record)

@app.post("/sessions/{session_id}/emergency-events", status_code=status.HTTP_201_CREATED)
async def create_emergency_event(
    session_id: UUID,
    payload: EmergencyEventCreate,
    connection: asyncpg.Connection = Depends(get_connection),
):
    record = await connection.fetchrow(
        """
        INSERT INTO emergency_events (
            session_id, trigger_id, source_message_id, detected_symptoms, alert_message
        )
        VALUES ($1, $2, $3, $4::jsonb, $5)
        RETURNING *
        """,
        session_id,
        payload.trigger_id,
        payload.source_message_id,
        payload.detected_symptoms,
        payload.alert_message,
    )
    return record_to_dict(record)

@app.get("/conversation-summary", response_model=list[ConversationSummaryOut])
async def conversation_summary(connection: asyncpg.Connection = Depends(get_connection)):
    records = await connection.fetch(
        "SELECT * FROM conversation_summary ORDER BY started_at DESC LIMIT 100"
)
    return records_to_dicts(records)
