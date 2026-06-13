from contextlib import asynccontextmanager
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import asyncpg
from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import create_pool, get_connection, record_to_dict, records_to_dicts
from app.schemas import (
    AnalyticsSummaryOut,
    AppointmentConfirm,
    AppointmentRequestCreate,
    AppointmentRequestOut,
    AppointmentStatus,
    AppointmentStatusUpdate,
    AppointmentSuggestAlternatives,
    AssessmentApprove,
    AssessmentModify,
    AssessmentReject,
    AssessmentResultCreate,
    AssessmentResultOut,
    AssessmentResultUpdate,
    AssessmentStatus,
    AuditLogOut,
    ConversationSummaryOut,
    DepartmentAvailabilityUpdate,
    DepartmentCreate,
    DepartmentOut,
    DepartmentRecommendationCreate,
    DepartmentRecommendationOut,
    DepartmentUpdate,
    EmergencyEventCreate,
    EmergencyEventOut,
    EmergencyTriggerCreate,
    EmergencyTriggerOut,
    EmergencyTriggerUpdate,
    FollowUpQuestionAnswer,
    FollowUpQuestionCreate,
    FollowUpQuestionOut,
    MessageCreate,
    MessageOut,
    RoutingFeedbackCreate,
    RoutingFeedbackOut,
    RoutingRuleCreate,
    RoutingRuleOut,
    RoutingRuleUpdate,
    SessionCreate,
    SessionOut,
    SessionUpdate,
    SeverityAssessmentCreate,
    SeverityAssessmentOut,
    SymptomEntryCreate,
    SymptomEntryOut,
    UrgencyLevel,
    UserCreate,
    UserOut,
    UserRole,
    UserUpdate,
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
async def foreign_key_violation_handler(
    request: Request,
    exc: asyncpg.ForeignKeyViolationError,
):
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "detail": (
                "Referenced record does not exist. Check session_id, user_id, "
                "message_id, assessment_id, department_id, or trigger_id."
            )
        },
    )


@app.exception_handler(asyncpg.UniqueViolationError)
async def unique_violation_handler(request: Request, exc: asyncpg.UniqueViolationError):
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": "Record already exists."},
    )


def json_ready(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {key: json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_ready(item) for item in value]
    return value


async def get_by_id(
    connection: asyncpg.Connection,
    table: str,
    record_id: UUID,
    detail: str,
) -> dict[str, Any]:
    record = await connection.fetchrow(f"SELECT * FROM {table} WHERE id = $1", record_id)
    if record is None:
        raise HTTPException(status_code=404, detail=detail)
    return record_to_dict(record)


async def update_by_id(
    connection: asyncpg.Connection,
    table: str,
    record_id: UUID,
    values: dict[str, Any],
    casts: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    casts = casts or {}
    if not values:
        record = await connection.fetchrow(f"SELECT * FROM {table} WHERE id = $1", record_id)
        return record_to_dict(record)

    args: list[Any] = [record_id]
    set_clauses: list[str] = []
    for field_name, value in values.items():
        args.append(value)
        set_clauses.append(f"{field_name} = ${len(args)}{casts.get(field_name, '')}")

    record = await connection.fetchrow(
        f"""
        UPDATE {table}
        SET {", ".join(set_clauses)}
        WHERE id = $1
        RETURNING *
        """,
        *args,
    )
    return record_to_dict(record)


async def write_audit_log(
    connection: asyncpg.Connection,
    actor_user_id: UUID | None,
    action: str,
    entity_type: str,
    entity_id: UUID | None,
    before_data: dict[str, Any] | None = None,
    after_data: dict[str, Any] | None = None,
) -> None:
    await connection.execute(
        """
        INSERT INTO audit_logs (
            actor_user_id, action, entity_type, entity_id, before_data, after_data
        )
        VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb)
        """,
        actor_user_id,
        action,
        entity_type,
        entity_id,
        json_ready(before_data),
        json_ready(after_data),
    )


@app.get("/")
async def root() -> dict[str, Any]:
    return {
        "name": settings.app_name,
        "status": "running",
        "docs": "/docs",
        "srs_version": "1.0",
        "resources": [
            "sessions",
            "messages",
            "symptoms",
            "follow-up-questions",
            "assessment-results",
            "appointments",
            "departments",
            "routing-rules",
            "emergency-triggers",
            "routing-feedback",
            "users",
            "analytics",
        ],
    }


@app.get("/health")
async def health(connection: asyncpg.Connection = Depends(get_connection)) -> dict[str, str]:
    await connection.fetchval("SELECT 1")
    return {"status": "ok", "environment": settings.environment}


@app.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    connection: asyncpg.Connection = Depends(get_connection),
):
    record = await connection.fetchrow(
        """
        INSERT INTO users (role, email, phone, full_name, is_active, metadata)
        VALUES ($1::user_role, $2, $3, $4, $5, $6::jsonb)
        RETURNING *
        """,
        payload.role,
        payload.email,
        payload.phone,
        payload.full_name,
        payload.is_active,
        payload.metadata,
    )
    user = record_to_dict(record)
    await write_audit_log(connection, user["id"], "create", "user", user["id"], None, user)
    return user


@app.get("/users", response_model=list[UserOut])
async def list_users(
    role: UserRole | None = None,
    is_active: bool | None = None,
    connection: asyncpg.Connection = Depends(get_connection),
):
    conditions: list[str] = []
    args: list[Any] = []

    if role is not None:
        args.append(role)
        conditions.append(f"role = ${len(args)}::user_role")
    if is_active is not None:
        args.append(is_active)
        conditions.append(f"is_active = ${len(args)}")

    where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    records = await connection.fetch(
        f"SELECT * FROM users {where_sql} ORDER BY created_at DESC",
        *args,
    )
    return records_to_dicts(records)


@app.get("/users/{user_id}", response_model=UserOut)
async def get_user(
    user_id: UUID,
    connection: asyncpg.Connection = Depends(get_connection),
):
    return await get_by_id(connection, "users", user_id, "User not found")


@app.patch("/users/{user_id}", response_model=UserOut)
async def update_user(
    user_id: UUID,
    payload: UserUpdate,
    connection: asyncpg.Connection = Depends(get_connection),
):
    before = await get_by_id(connection, "users", user_id, "User not found")
    values = payload.model_dump(exclude_unset=True)
    user = await update_by_id(
        connection,
        "users",
        user_id,
        values,
        casts={"role": "::user_role", "metadata": "::jsonb"},
    )
    await write_audit_log(connection, user_id, "update", "user", user_id, before, user)
    return user


@app.delete("/users/{user_id}", response_model=UserOut)
async def deactivate_user(
    user_id: UUID,
    connection: asyncpg.Connection = Depends(get_connection),
):
    before = await get_by_id(connection, "users", user_id, "User not found")
    user = await update_by_id(connection, "users", user_id, {"is_active": False})
    await write_audit_log(connection, user_id, "deactivate", "user", user_id, before, user)
    return user


@app.post("/sessions", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
async def create_session(
    payload: SessionCreate,
    connection: asyncpg.Connection = Depends(get_connection),
):
    record = await connection.fetchrow(
        """
        INSERT INTO sessions (language, patient_user_id, user_agent, ip_hash, metadata)
        VALUES ($1::language_code, $2, $3, $4, $5::jsonb)
        RETURNING *
        """,
        payload.language,
        payload.patient_user_id,
        payload.user_agent,
        payload.ip_hash,
        payload.metadata,
    )
    return record_to_dict(record)


@app.get("/sessions/{session_id}", response_model=SessionOut)
async def get_session(
    session_id: UUID,
    connection: asyncpg.Connection = Depends(get_connection),
):
    return await get_by_id(connection, "sessions", session_id, "Session not found")


@app.patch("/sessions/{session_id}", response_model=SessionOut)
async def update_session(
    session_id: UUID,
    payload: SessionUpdate,
    connection: asyncpg.Connection = Depends(get_connection),
):
    ended_sql = "NOW()" if payload.status in {"completed", "reset", "escalated"} else "ended_at"
    record = await connection.fetchrow(
        f"""
        UPDATE sessions
        SET status = $2::session_status, ended_at = {ended_sql}
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
async def create_message(
    session_id: UUID,
    payload: MessageCreate,
    connection: asyncpg.Connection = Depends(get_connection),
):
    record = await connection.fetchrow(
        """
        INSERT INTO messages (
            session_id, role, input_mode, content, audio_url, transcript_confidence,
            model_name, response_latency_ms, metadata
        )
        VALUES ($1, $2::message_role, $3::input_mode, $4, $5, $6, $7, $8, $9::jsonb)
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
async def list_messages(
    session_id: UUID,
    connection: asyncpg.Connection = Depends(get_connection),
):
    records = await connection.fetch(
        "SELECT * FROM messages WHERE session_id = $1 ORDER BY created_at ASC",
        session_id,
    )
    return records_to_dicts(records)


@app.get("/sessions/{session_id}/context")
async def get_assessment_context(
    session_id: UUID,
    connection: asyncpg.Connection = Depends(get_connection),
):
    session = await get_by_id(connection, "sessions", session_id, "Session not found")
    messages = await connection.fetch(
        "SELECT * FROM messages WHERE session_id = $1 ORDER BY created_at ASC",
        session_id,
    )
    symptoms = await connection.fetch(
        "SELECT * FROM symptom_entries WHERE session_id = $1 ORDER BY created_at ASC",
        session_id,
    )
    questions = await connection.fetch(
        "SELECT * FROM follow_up_questions WHERE session_id = $1 ORDER BY asked_at ASC",
        session_id,
    )
    latest_result = await connection.fetchrow(
        """
        SELECT * FROM assessment_results
        WHERE session_id = $1
        ORDER BY created_at DESC
        LIMIT 1
        """,
        session_id,
    )
    return {
        "session": session,
        "messages": records_to_dicts(messages),
        "symptoms": records_to_dicts(symptoms),
        "follow_up_questions": records_to_dicts(questions),
        "latest_assessment_result": record_to_dict(latest_result),
    }


@app.post("/sessions/{session_id}/symptoms", response_model=SymptomEntryOut, status_code=status.HTTP_201_CREATED)
async def create_symptom_entry(
    session_id: UUID,
    payload: SymptomEntryCreate,
    connection: asyncpg.Connection = Depends(get_connection),
):
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


@app.get("/sessions/{session_id}/symptoms", response_model=list[SymptomEntryOut])
async def list_symptom_entries(
    session_id: UUID,
    connection: asyncpg.Connection = Depends(get_connection),
):
    records = await connection.fetch(
        "SELECT * FROM symptom_entries WHERE session_id = $1 ORDER BY created_at ASC",
        session_id,
    )
    return records_to_dicts(records)


@app.post(
    "/sessions/{session_id}/follow-up-questions",
    response_model=FollowUpQuestionOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_follow_up_question(
    session_id: UUID,
    payload: FollowUpQuestionCreate,
    connection: asyncpg.Connection = Depends(get_connection),
):
    record = await connection.fetchrow(
        """
        INSERT INTO follow_up_questions (session_id, question_text, reason)
        VALUES ($1, $2, $3)
        RETURNING *
        """,
        session_id,
        payload.question_text,
        payload.reason,
    )
    return record_to_dict(record)


@app.get("/sessions/{session_id}/follow-up-questions", response_model=list[FollowUpQuestionOut])
async def list_follow_up_questions(
    session_id: UUID,
    connection: asyncpg.Connection = Depends(get_connection),
):
    records = await connection.fetch(
        "SELECT * FROM follow_up_questions WHERE session_id = $1 ORDER BY asked_at ASC",
        session_id,
    )
    return records_to_dicts(records)


@app.patch("/follow-up-questions/{question_id}/answer", response_model=FollowUpQuestionOut)
async def answer_follow_up_question(
    question_id: UUID,
    payload: FollowUpQuestionAnswer,
    connection: asyncpg.Connection = Depends(get_connection),
):
    record = await connection.fetchrow(
        """
        UPDATE follow_up_questions
        SET answer_message_id = $2, answered_at = NOW()
        WHERE id = $1
        RETURNING *
        """,
        question_id,
        payload.answer_message_id,
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Follow-up question not found")
    return record_to_dict(record)


@app.post(
    "/sessions/{session_id}/severity-assessments",
    response_model=SeverityAssessmentOut,
    status_code=status.HTTP_201_CREATED,
)
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
        VALUES ($1, $2, $3::severity_level, $4, $5, $6::jsonb)
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


@app.get("/sessions/{session_id}/severity-assessments", response_model=list[SeverityAssessmentOut])
async def list_severity_assessments(
    session_id: UUID,
    connection: asyncpg.Connection = Depends(get_connection),
):
    records = await connection.fetch(
        "SELECT * FROM severity_assessments WHERE session_id = $1 ORDER BY created_at DESC",
        session_id,
    )
    return records_to_dicts(records)


@app.post(
    "/sessions/{session_id}/department-recommendations",
    response_model=DepartmentRecommendationOut,
    status_code=status.HTTP_201_CREATED,
)
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


@app.get("/sessions/{session_id}/department-recommendations", response_model=list[DepartmentRecommendationOut])
async def list_department_recommendations(
    session_id: UUID,
    connection: asyncpg.Connection = Depends(get_connection),
):
    records = await connection.fetch(
        """
        SELECT * FROM department_recommendations
        WHERE session_id = $1
        ORDER BY created_at DESC
        """,
        session_id,
    )
    return records_to_dicts(records)


@app.post(
    "/sessions/{session_id}/emergency-events",
    response_model=EmergencyEventOut,
    status_code=status.HTTP_201_CREATED,
)
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


@app.get("/sessions/{session_id}/emergency-events", response_model=list[EmergencyEventOut])
async def list_emergency_events(
    session_id: UUID,
    connection: asyncpg.Connection = Depends(get_connection),
):
    records = await connection.fetch(
        "SELECT * FROM emergency_events WHERE session_id = $1 ORDER BY created_at DESC",
        session_id,
    )
    return records_to_dicts(records)


@app.post(
    "/sessions/{session_id}/assessment-results",
    response_model=AssessmentResultOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_assessment_result(
    session_id: UUID,
    payload: AssessmentResultCreate,
    connection: asyncpg.Connection = Depends(get_connection),
):
    record = await connection.fetchrow(
        """
        INSERT INTO assessment_results (
            session_id, source_assessment_id, recommendation_id, summary, urgency,
            department_id, confidence, ai_metadata
        )
        VALUES ($1, $2, $3, $4, $5::urgency_level, $6, $7, $8::jsonb)
        RETURNING *
        """,
        session_id,
        payload.source_assessment_id,
        payload.recommendation_id,
        payload.summary,
        payload.urgency,
        payload.department_id,
        payload.confidence,
        payload.ai_metadata,
    )
    return record_to_dict(record)


@app.get("/sessions/{session_id}/assessment-results", response_model=list[AssessmentResultOut])
async def list_session_assessment_results(
    session_id: UUID,
    connection: asyncpg.Connection = Depends(get_connection),
):
    records = await connection.fetch(
        """
        SELECT * FROM assessment_results
        WHERE session_id = $1
        ORDER BY created_at DESC
        """,
        session_id,
    )
    return records_to_dicts(records)


@app.get("/assessment-results/{assessment_result_id}", response_model=AssessmentResultOut)
async def get_assessment_result(
    assessment_result_id: UUID,
    connection: asyncpg.Connection = Depends(get_connection),
):
    return await get_by_id(
        connection,
        "assessment_results",
        assessment_result_id,
        "Assessment result not found",
    )


@app.patch("/assessment-results/{assessment_result_id}", response_model=AssessmentResultOut)
async def update_assessment_result(
    assessment_result_id: UUID,
    payload: AssessmentResultUpdate,
    connection: asyncpg.Connection = Depends(get_connection),
):
    before = await get_by_id(
        connection,
        "assessment_results",
        assessment_result_id,
        "Assessment result not found",
    )
    values = payload.model_dump(exclude_unset=True)
    result = await update_by_id(
        connection,
        "assessment_results",
        assessment_result_id,
        values,
        casts={
            "urgency": "::urgency_level",
            "status": "::assessment_status",
            "ai_metadata": "::jsonb",
        },
    )
    await write_audit_log(
        connection,
        None,
        "update",
        "assessment_result",
        assessment_result_id,
        before,
        result,
    )
    return result


@app.get("/nurse/assessment-results", response_model=list[AssessmentResultOut])
async def nurse_assessment_queue(
    review_status: AssessmentStatus | None = Query(default=None, alias="status"),
    urgency: UrgencyLevel | None = None,
    connection: asyncpg.Connection = Depends(get_connection),
):
    conditions: list[str] = []
    args: list[Any] = []

    if review_status is not None:
        args.append(review_status)
        conditions.append(f"status = ${len(args)}::assessment_status")
    if urgency is not None:
        args.append(urgency)
        conditions.append(f"urgency = ${len(args)}::urgency_level")

    where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    records = await connection.fetch(
        f"""
        SELECT * FROM assessment_results
        {where_sql}
        ORDER BY created_at DESC
        LIMIT 200
        """,
        *args,
    )
    return records_to_dicts(records)


@app.post("/assessment-results/{assessment_result_id}/approve", response_model=AssessmentResultOut)
async def approve_assessment_result(
    assessment_result_id: UUID,
    payload: AssessmentApprove,
    connection: asyncpg.Connection = Depends(get_connection),
):
    before = await get_by_id(
        connection,
        "assessment_results",
        assessment_result_id,
        "Assessment result not found",
    )
    record = await connection.fetchrow(
        """
        UPDATE assessment_results
        SET status = 'approved',
            final_urgency = urgency,
            final_department_id = department_id,
            nurse_user_id = $2,
            nurse_notes = $3,
            rejection_reason = NULL,
            reviewed_at = NOW()
        WHERE id = $1
        RETURNING *
        """,
        assessment_result_id,
        payload.nurse_user_id,
        payload.nurse_notes,
    )
    result = record_to_dict(record)
    await write_audit_log(
        connection,
        payload.nurse_user_id,
        "approve",
        "assessment_result",
        assessment_result_id,
        before,
        result,
    )
    return result


@app.post("/assessment-results/{assessment_result_id}/modify", response_model=AssessmentResultOut)
async def modify_assessment_result(
    assessment_result_id: UUID,
    payload: AssessmentModify,
    connection: asyncpg.Connection = Depends(get_connection),
):
    before = await get_by_id(
        connection,
        "assessment_results",
        assessment_result_id,
        "Assessment result not found",
    )
    record = await connection.fetchrow(
        """
        UPDATE assessment_results
        SET status = 'modified',
            final_urgency = $2::urgency_level,
            final_department_id = $3,
            nurse_user_id = $4,
            nurse_notes = $5,
            rejection_reason = NULL,
            reviewed_at = NOW()
        WHERE id = $1
        RETURNING *
        """,
        assessment_result_id,
        payload.final_urgency,
        payload.final_department_id,
        payload.nurse_user_id,
        payload.nurse_notes,
    )
    result = record_to_dict(record)
    await write_audit_log(
        connection,
        payload.nurse_user_id,
        "modify",
        "assessment_result",
        assessment_result_id,
        before,
        result,
    )
    return result


@app.post("/assessment-results/{assessment_result_id}/reject", response_model=AssessmentResultOut)
async def reject_assessment_result(
    assessment_result_id: UUID,
    payload: AssessmentReject,
    connection: asyncpg.Connection = Depends(get_connection),
):
    before = await get_by_id(
        connection,
        "assessment_results",
        assessment_result_id,
        "Assessment result not found",
    )
    record = await connection.fetchrow(
        """
        UPDATE assessment_results
        SET status = 'rejected',
            final_urgency = NULL,
            final_department_id = NULL,
            nurse_user_id = $2,
            nurse_notes = $3,
            rejection_reason = $4,
            reviewed_at = NOW()
        WHERE id = $1
        RETURNING *
        """,
        assessment_result_id,
        payload.nurse_user_id,
        payload.nurse_notes,
        payload.rejection_reason,
    )
    result = record_to_dict(record)
    await write_audit_log(
        connection,
        payload.nurse_user_id,
        "reject",
        "assessment_result",
        assessment_result_id,
        before,
        result,
    )
    return result


@app.get("/departments", response_model=list[DepartmentOut])
async def list_departments(
    include_inactive: bool = False,
    connection: asyncpg.Connection = Depends(get_connection),
):
    where_sql = "" if include_inactive else "WHERE is_active = TRUE"
    records = await connection.fetch(
        f"SELECT * FROM departments {where_sql} ORDER BY name_en ASC"
    )
    return records_to_dicts(records)


@app.post("/departments", response_model=DepartmentOut, status_code=status.HTTP_201_CREATED)
async def create_department(
    payload: DepartmentCreate,
    connection: asyncpg.Connection = Depends(get_connection),
):
    record = await connection.fetchrow(
        """
        INSERT INTO departments (
            code, name_en, name_th, description_en, description_th, is_active,
            availability_status, accepting_appointments, unavailable_reason,
            next_available_date, capacity_per_day
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7::department_availability_status, $8, $9, $10, $11)
        RETURNING *
        """,
        payload.code,
        payload.name_en,
        payload.name_th,
        payload.description_en,
        payload.description_th,
        payload.is_active,
        payload.availability_status,
        payload.accepting_appointments,
        payload.unavailable_reason,
        payload.next_available_date,
        payload.capacity_per_day,
    )
    department = record_to_dict(record)
    await write_audit_log(connection, None, "create", "department", department["id"], None, department)
    return department


@app.get("/departments/{department_id}", response_model=DepartmentOut)
async def get_department(
    department_id: UUID,
    connection: asyncpg.Connection = Depends(get_connection),
):
    return await get_by_id(connection, "departments", department_id, "Department not found")


@app.patch("/departments/{department_id}", response_model=DepartmentOut)
async def update_department(
    department_id: UUID,
    payload: DepartmentUpdate,
    connection: asyncpg.Connection = Depends(get_connection),
):
    before = await get_by_id(connection, "departments", department_id, "Department not found")
    values = payload.model_dump(exclude_unset=True)
    department = await update_by_id(
        connection,
        "departments",
        department_id,
        values,
        casts={"availability_status": "::department_availability_status"},
    )
    await write_audit_log(
        connection,
        None,
        "update",
        "department",
        department_id,
        before,
        department,
    )
    return department


@app.patch("/departments/{department_id}/availability", response_model=DepartmentOut)
async def update_department_availability(
    department_id: UUID,
    payload: DepartmentAvailabilityUpdate,
    connection: asyncpg.Connection = Depends(get_connection),
):
    before = await get_by_id(connection, "departments", department_id, "Department not found")
    values = payload.model_dump(exclude_unset=True)
    if "accepting_appointments" not in values:
        values["accepting_appointments"] = payload.availability_status != "unavailable"
    department = await update_by_id(
        connection,
        "departments",
        department_id,
        values,
        casts={"availability_status": "::department_availability_status"},
    )
    await write_audit_log(
        connection,
        None,
        "update_availability",
        "department",
        department_id,
        before,
        department,
    )
    return department


@app.delete("/departments/{department_id}", response_model=DepartmentOut)
async def deactivate_department(
    department_id: UUID,
    connection: asyncpg.Connection = Depends(get_connection),
):
    before = await get_by_id(connection, "departments", department_id, "Department not found")
    department = await update_by_id(connection, "departments", department_id, {"is_active": False})
    await write_audit_log(
        connection,
        None,
        "deactivate",
        "department",
        department_id,
        before,
        department,
    )
    return department


@app.get("/routing-rules", response_model=list[RoutingRuleOut])
async def list_routing_rules(
    include_inactive: bool = False,
    department_id: UUID | None = None,
    connection: asyncpg.Connection = Depends(get_connection),
):
    conditions: list[str] = []
    args: list[Any] = []
    if not include_inactive:
        conditions.append("is_active = TRUE")
    if department_id is not None:
        args.append(department_id)
        conditions.append(f"department_id = ${len(args)}")
    where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    records = await connection.fetch(
        f"""
        SELECT * FROM routing_rules
        {where_sql}
        ORDER BY priority ASC, rule_name ASC
        """,
        *args,
    )
    return records_to_dicts(records)


@app.post("/routing-rules", response_model=RoutingRuleOut, status_code=status.HTTP_201_CREATED)
async def create_routing_rule(
    payload: RoutingRuleCreate,
    connection: asyncpg.Connection = Depends(get_connection),
):
    record = await connection.fetchrow(
        """
        INSERT INTO routing_rules (
            department_id, rule_name, description, symptom_keywords, condition_json,
            severity_override, priority, is_active, created_by, updated_by
        )
        VALUES ($1, $2, $3, $4::text[], $5::jsonb, $6::severity_level, $7, $8, $9, $10)
        RETURNING *
        """,
        payload.department_id,
        payload.rule_name,
        payload.description,
        payload.symptom_keywords,
        payload.condition_json,
        payload.severity_override,
        payload.priority,
        payload.is_active,
        payload.created_by,
        payload.updated_by,
    )
    rule = record_to_dict(record)
    await write_audit_log(connection, None, "create", "routing_rule", rule["id"], None, rule)
    return rule


@app.get("/routing-rules/{rule_id}", response_model=RoutingRuleOut)
async def get_routing_rule(
    rule_id: UUID,
    connection: asyncpg.Connection = Depends(get_connection),
):
    return await get_by_id(connection, "routing_rules", rule_id, "Routing rule not found")


@app.patch("/routing-rules/{rule_id}", response_model=RoutingRuleOut)
async def update_routing_rule(
    rule_id: UUID,
    payload: RoutingRuleUpdate,
    connection: asyncpg.Connection = Depends(get_connection),
):
    before = await get_by_id(connection, "routing_rules", rule_id, "Routing rule not found")
    values = payload.model_dump(exclude_unset=True)
    rule = await update_by_id(
        connection,
        "routing_rules",
        rule_id,
        values,
        casts={
            "symptom_keywords": "::text[]",
            "condition_json": "::jsonb",
            "severity_override": "::severity_level",
        },
    )
    await write_audit_log(connection, None, "update", "routing_rule", rule_id, before, rule)
    return rule


@app.delete("/routing-rules/{rule_id}", response_model=RoutingRuleOut)
async def deactivate_routing_rule(
    rule_id: UUID,
    connection: asyncpg.Connection = Depends(get_connection),
):
    before = await get_by_id(connection, "routing_rules", rule_id, "Routing rule not found")
    rule = await update_by_id(connection, "routing_rules", rule_id, {"is_active": False})
    await write_audit_log(connection, None, "deactivate", "routing_rule", rule_id, before, rule)
    return rule


@app.get("/emergency-triggers", response_model=list[EmergencyTriggerOut])
async def list_emergency_triggers(
    include_inactive: bool = False,
    connection: asyncpg.Connection = Depends(get_connection),
):
    where_sql = "" if include_inactive else "WHERE is_active = TRUE"
    records = await connection.fetch(
        f"""
        SELECT * FROM emergency_triggers
        {where_sql}
        ORDER BY priority ASC, trigger_name ASC
        """
    )
    return records_to_dicts(records)


@app.post("/emergency-triggers", response_model=EmergencyTriggerOut, status_code=status.HTTP_201_CREATED)
async def create_emergency_trigger(
    payload: EmergencyTriggerCreate,
    connection: asyncpg.Connection = Depends(get_connection),
):
    record = await connection.fetchrow(
        """
        INSERT INTO emergency_triggers (
            trigger_name, description, trigger_keywords, condition_json,
            alert_message_en, alert_message_th, priority, is_active, created_by, updated_by
        )
        VALUES ($1, $2, $3::text[], $4::jsonb, $5, $6, $7, $8, $9, $10)
        RETURNING *
        """,
        payload.trigger_name,
        payload.description,
        payload.trigger_keywords,
        payload.condition_json,
        payload.alert_message_en,
        payload.alert_message_th,
        payload.priority,
        payload.is_active,
        payload.created_by,
        payload.updated_by,
    )
    trigger = record_to_dict(record)
    await write_audit_log(
        connection,
        None,
        "create",
        "emergency_trigger",
        trigger["id"],
        None,
        trigger,
    )
    return trigger


@app.get("/emergency-triggers/{trigger_id}", response_model=EmergencyTriggerOut)
async def get_emergency_trigger(
    trigger_id: UUID,
    connection: asyncpg.Connection = Depends(get_connection),
):
    return await get_by_id(
        connection,
        "emergency_triggers",
        trigger_id,
        "Emergency trigger not found",
    )


@app.patch("/emergency-triggers/{trigger_id}", response_model=EmergencyTriggerOut)
async def update_emergency_trigger(
    trigger_id: UUID,
    payload: EmergencyTriggerUpdate,
    connection: asyncpg.Connection = Depends(get_connection),
):
    before = await get_by_id(
        connection,
        "emergency_triggers",
        trigger_id,
        "Emergency trigger not found",
    )
    values = payload.model_dump(exclude_unset=True)
    trigger = await update_by_id(
        connection,
        "emergency_triggers",
        trigger_id,
        values,
        casts={"trigger_keywords": "::text[]", "condition_json": "::jsonb"},
    )
    await write_audit_log(
        connection,
        None,
        "update",
        "emergency_trigger",
        trigger_id,
        before,
        trigger,
    )
    return trigger


@app.delete("/emergency-triggers/{trigger_id}", response_model=EmergencyTriggerOut)
async def deactivate_emergency_trigger(
    trigger_id: UUID,
    connection: asyncpg.Connection = Depends(get_connection),
):
    before = await get_by_id(
        connection,
        "emergency_triggers",
        trigger_id,
        "Emergency trigger not found",
    )
    trigger = await update_by_id(
        connection,
        "emergency_triggers",
        trigger_id,
        {"is_active": False},
    )
    await write_audit_log(
        connection,
        None,
        "deactivate",
        "emergency_trigger",
        trigger_id,
        before,
        trigger,
    )
    return trigger


async def resolve_appointment_defaults(
    connection: asyncpg.Connection,
    session_id: UUID,
    payload: AppointmentRequestCreate,
) -> tuple[UUID | None, UUID | None]:
    patient_user_id = payload.patient_user_id
    department_id = payload.department_id

    if patient_user_id is None:
        session = await connection.fetchrow(
            "SELECT patient_user_id FROM sessions WHERE id = $1",
            session_id,
        )
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
        patient_user_id = session["patient_user_id"]

    if department_id is None and payload.assessment_result_id is not None:
        result = await connection.fetchrow(
            """
            SELECT COALESCE(final_department_id, department_id) AS department_id
            FROM assessment_results
            WHERE id = $1
            """,
            payload.assessment_result_id,
        )
        if result is None:
            raise HTTPException(status_code=404, detail="Assessment result not found")
        department_id = result["department_id"]

    return patient_user_id, department_id


@app.post(
    "/sessions/{session_id}/appointment-requests",
    response_model=AppointmentRequestOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_appointment_request(
    session_id: UUID,
    payload: AppointmentRequestCreate,
    connection: asyncpg.Connection = Depends(get_connection),
):
    patient_user_id, department_id = await resolve_appointment_defaults(
        connection,
        session_id,
        payload,
    )
    record = await connection.fetchrow(
        """
        INSERT INTO appointment_requests (
            session_id, assessment_result_id, patient_user_id, department_id,
            requested_date, requested_time, reason
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        RETURNING *
        """,
        session_id,
        payload.assessment_result_id,
        patient_user_id,
        department_id,
        payload.requested_date,
        payload.requested_time,
        payload.reason,
    )
    return record_to_dict(record)


@app.get("/sessions/{session_id}/appointment-requests", response_model=list[AppointmentRequestOut])
async def list_session_appointment_requests(
    session_id: UUID,
    connection: asyncpg.Connection = Depends(get_connection),
):
    records = await connection.fetch(
        """
        SELECT * FROM appointment_requests
        WHERE session_id = $1
        ORDER BY created_at DESC
        """,
        session_id,
    )
    return records_to_dicts(records)


@app.get("/appointment-requests", response_model=list[AppointmentRequestOut])
async def list_appointment_requests(
    request_status: AppointmentStatus | None = Query(default=None, alias="status"),
    department_id: UUID | None = None,
    connection: asyncpg.Connection = Depends(get_connection),
):
    conditions: list[str] = []
    args: list[Any] = []
    if request_status is not None:
        args.append(request_status)
        conditions.append(f"status = ${len(args)}::appointment_status")
    if department_id is not None:
        args.append(department_id)
        conditions.append(f"department_id = ${len(args)}")
    where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    records = await connection.fetch(
        f"""
        SELECT * FROM appointment_requests
        {where_sql}
        ORDER BY created_at DESC
        LIMIT 200
        """,
        *args,
    )
    return records_to_dicts(records)


@app.get("/appointment-requests/{appointment_id}", response_model=AppointmentRequestOut)
async def get_appointment_request(
    appointment_id: UUID,
    connection: asyncpg.Connection = Depends(get_connection),
):
    return await get_by_id(
        connection,
        "appointment_requests",
        appointment_id,
        "Appointment request not found",
    )


@app.post("/appointment-requests/{appointment_id}/confirm", response_model=AppointmentRequestOut)
async def confirm_appointment_request(
    appointment_id: UUID,
    payload: AppointmentConfirm,
    connection: asyncpg.Connection = Depends(get_connection),
):
    before = await get_by_id(
        connection,
        "appointment_requests",
        appointment_id,
        "Appointment request not found",
    )
    record = await connection.fetchrow(
        """
        UPDATE appointment_requests
        SET status = 'confirmed',
            confirmed_date = $2,
            confirmed_time = $3,
            nurse_user_id = $4,
            nurse_notes = $5
        WHERE id = $1
        RETURNING *
        """,
        appointment_id,
        payload.confirmed_date,
        payload.confirmed_time,
        payload.nurse_user_id,
        payload.nurse_notes,
    )
    appointment = record_to_dict(record)
    await write_audit_log(
        connection,
        payload.nurse_user_id,
        "confirm",
        "appointment_request",
        appointment_id,
        before,
        appointment,
    )
    return appointment


@app.post("/appointment-requests/{appointment_id}/suggest-alternatives", response_model=AppointmentRequestOut)
async def suggest_alternative_appointments(
    appointment_id: UUID,
    payload: AppointmentSuggestAlternatives,
    connection: asyncpg.Connection = Depends(get_connection),
):
    before = await get_by_id(
        connection,
        "appointment_requests",
        appointment_id,
        "Appointment request not found",
    )
    alternatives = [item.isoformat() for item in payload.alternative_dates]
    record = await connection.fetchrow(
        """
        UPDATE appointment_requests
        SET status = 'alternative_suggested',
            alternative_dates = $2::jsonb,
            nurse_user_id = $3,
            nurse_notes = $4
        WHERE id = $1
        RETURNING *
        """,
        appointment_id,
        alternatives,
        payload.nurse_user_id,
        payload.nurse_notes,
    )
    appointment = record_to_dict(record)
    await write_audit_log(
        connection,
        payload.nurse_user_id,
        "suggest_alternatives",
        "appointment_request",
        appointment_id,
        before,
        appointment,
    )
    return appointment


@app.patch("/appointment-requests/{appointment_id}", response_model=AppointmentRequestOut)
async def update_appointment_status(
    appointment_id: UUID,
    payload: AppointmentStatusUpdate,
    connection: asyncpg.Connection = Depends(get_connection),
):
    before = await get_by_id(
        connection,
        "appointment_requests",
        appointment_id,
        "Appointment request not found",
    )
    record = await connection.fetchrow(
        """
        UPDATE appointment_requests
        SET status = $2::appointment_status,
            nurse_user_id = COALESCE($3, nurse_user_id),
            nurse_notes = COALESCE($4, nurse_notes)
        WHERE id = $1
        RETURNING *
        """,
        appointment_id,
        payload.status,
        payload.nurse_user_id,
        payload.nurse_notes,
    )
    appointment = record_to_dict(record)
    await write_audit_log(
        connection,
        payload.nurse_user_id,
        "update_status",
        "appointment_request",
        appointment_id,
        before,
        appointment,
    )
    return appointment


@app.post(
    "/assessment-results/{assessment_result_id}/routing-feedback",
    response_model=RoutingFeedbackOut,
    status_code=status.HTTP_201_CREATED,
)
async def submit_routing_feedback(
    assessment_result_id: UUID,
    payload: RoutingFeedbackCreate,
    connection: asyncpg.Connection = Depends(get_connection),
):
    assessment = await get_by_id(
        connection,
        "assessment_results",
        assessment_result_id,
        "Assessment result not found",
    )
    original_department_id = payload.original_department_id or assessment["department_id"]
    original_urgency = payload.original_urgency or assessment["urgency"]

    record = await connection.fetchrow(
        """
        INSERT INTO routing_feedback (
            assessment_result_id, session_id, nurse_user_id, original_department_id,
            corrected_department_id, original_urgency, corrected_urgency, feedback_text
        )
        VALUES ($1, $2, $3, $4, $5, $6::urgency_level, $7::urgency_level, $8)
        RETURNING *
        """,
        assessment_result_id,
        assessment["session_id"],
        payload.nurse_user_id,
        original_department_id,
        payload.corrected_department_id,
        original_urgency,
        payload.corrected_urgency,
        payload.feedback_text,
    )
    feedback = record_to_dict(record)
    await write_audit_log(
        connection,
        payload.nurse_user_id,
        "create",
        "routing_feedback",
        feedback["id"],
        None,
        feedback,
    )
    return feedback


@app.get("/routing-feedback", response_model=list[RoutingFeedbackOut])
async def list_routing_feedback(
    assessment_result_id: UUID | None = None,
    session_id: UUID | None = None,
    connection: asyncpg.Connection = Depends(get_connection),
):
    conditions: list[str] = []
    args: list[Any] = []
    if assessment_result_id is not None:
        args.append(assessment_result_id)
        conditions.append(f"assessment_result_id = ${len(args)}")
    if session_id is not None:
        args.append(session_id)
        conditions.append(f"session_id = ${len(args)}")
    where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    records = await connection.fetch(
        f"""
        SELECT * FROM routing_feedback
        {where_sql}
        ORDER BY created_at DESC
        LIMIT 200
        """,
        *args,
    )
    return records_to_dicts(records)


@app.get("/analytics/summary", response_model=AnalyticsSummaryOut)
async def analytics_summary(connection: asyncpg.Connection = Depends(get_connection)):
    total_sessions = await connection.fetchval("SELECT COUNT(*) FROM sessions")
    total_results = await connection.fetchval("SELECT COUNT(*) FROM assessment_results")
    total_appointments = await connection.fetchval("SELECT COUNT(*) FROM appointment_requests")

    review_counts = {
        record["status"]: record["count"]
        for record in await connection.fetch(
            "SELECT status::text AS status, COUNT(*)::int AS count FROM assessment_results GROUP BY status"
        )
    }
    appointment_counts = {
        record["status"]: record["count"]
        for record in await connection.fetch(
            "SELECT status::text AS status, COUNT(*)::int AS count FROM appointment_requests GROUP BY status"
        )
    }
    urgency_distribution = {
        record["urgency"]: record["count"]
        for record in await connection.fetch(
            """
            SELECT COALESCE(final_urgency, urgency)::text AS urgency, COUNT(*)::int AS count
            FROM assessment_results
            GROUP BY COALESCE(final_urgency, urgency)
            """
        )
    }
    department_distribution = {
        record["department_name"]: record["count"]
        for record in await connection.fetch(
            """
            SELECT COALESCE(d.name_en, 'Unassigned') AS department_name, COUNT(*)::int AS count
            FROM assessment_results ar
            LEFT JOIN departments d ON d.id = COALESCE(ar.final_department_id, ar.department_id)
            GROUP BY COALESCE(d.name_en, 'Unassigned')
            ORDER BY count DESC
            """
        )
    }

    return {
        "total_sessions": total_sessions,
        "total_assessment_results": total_results,
        "pending_reviews": review_counts.get("pending_review", 0),
        "approved_reviews": review_counts.get("approved", 0),
        "modified_reviews": review_counts.get("modified", 0),
        "rejected_reviews": review_counts.get("rejected", 0),
        "total_appointments": total_appointments,
        "pending_appointments": appointment_counts.get("pending", 0),
        "confirmed_appointments": appointment_counts.get("confirmed", 0),
        "urgency_distribution": urgency_distribution,
        "department_distribution": department_distribution,
    }


@app.get("/analytics/assessment-summary")
async def opd_assessment_summary(
    limit: int = Query(default=100, ge=1, le=500),
    connection: asyncpg.Connection = Depends(get_connection),
):
    records = await connection.fetch(
        """
        SELECT * FROM opd_assessment_summary
        ORDER BY started_at DESC
        LIMIT $1
        """,
        limit,
    )
    return records_to_dicts(records)


@app.get("/audit-logs", response_model=list[AuditLogOut])
async def list_audit_logs(
    limit: int = Query(default=100, ge=1, le=500),
    connection: asyncpg.Connection = Depends(get_connection),
):
    records = await connection.fetch(
        """
        SELECT * FROM audit_logs
        ORDER BY created_at DESC
        LIMIT $1
        """,
        limit,
    )
    return records_to_dicts(records)


@app.get("/conversation-summary", response_model=list[ConversationSummaryOut])
async def conversation_summary(connection: asyncpg.Connection = Depends(get_connection)):
    records = await connection.fetch(
        "SELECT * FROM conversation_summary ORDER BY started_at DESC LIMIT 100"
    )
    return records_to_dicts(records)
