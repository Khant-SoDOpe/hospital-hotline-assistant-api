from datetime import datetime
from typing import Any, Literal
from uuid import UUID
from pydantic import BaseModel, Field

LanguageCode = Literal["th", "en"]
SessionStatus = Literal["active", "completed", "reset", "escalated"]
MessageRole = Literal["user", "assistant", "system"]
InputMode = Literal["voice", "text"]
SeverityLevel = Literal["emergency", "urgent", "general", "unknown"]

class SessionCreate(BaseModel):
    language: LanguageCode = "th"
    user_agent: str | None = None
    ip_hash: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

class SessionUpdate(BaseModel):
    status: SessionStatus

class SessionOut(BaseModel):
    id: UUID
    language: LanguageCode
    status: SessionStatus
    started_at: datetime
    ended_at: datetime | None = None
    user_agent: str | None = None
    ip_hash: str | None = None
    metadata: dict[str, Any]

class MessageCreate(BaseModel):
    role: MessageRole
    input_mode: InputMode | None = None
    content: str
    audio_url: str | None = None
    transcript_confidence: float | None = Field(default=None, ge=0, le=1)
    model_name: str | None = None
    response_latency_ms: int | None = Field(default=None, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

class MessageOut(MessageCreate):
    id: UUID
    session_id: UUID
    created_at: datetime

class SymptomEntryCreate(BaseModel):
    message_id: UUID | None = None
    raw_text: str
    normalized_symptoms: list[Any] = Field(default_factory=list)
    body_location: str | None = None
    duration_text: str | None = None
    pain_score: int | None = Field(default=None, ge=0, le=10)

class SeverityAssessmentCreate(BaseModel):
    source_message_id: UUID | None = None
    severity: SeverityLevel = "unknown"
    confidence: float | None = Field(default=None, ge=0, le=1)
    explanation: str | None = None
    detected_triggers: list[Any] = Field(default_factory=list)

class DepartmentOut(BaseModel):
    id: UUID
    code: str
    name_en: str
    name_th: str | None = None
    description_en: str | None = None
    description_th: str | None = None
    is_active: bool

class RoutingRuleOut(BaseModel):
    id: UUID
    department_id: UUID
    rule_name: str
    description: str | None = None
    symptom_keywords: list[str]
    condition_json: dict[str, Any]
    severity_override: SeverityLevel | None = None
    priority: int
    is_active: bool

class EmergencyTriggerOut(BaseModel):
    id: UUID
    trigger_name: str
    description: str | None = None
    trigger_keywords: list[str]
    condition_json: dict[str, Any]
    alert_message_en: str
    alert_message_th: str | None = None
    priority: int
    is_active: bool

class DepartmentRecommendationCreate(BaseModel):
    assessment_id: UUID | None = None
    department_id: UUID
    confidence: float | None = Field(default=None, ge=0, le=1)
    reason: str | None = None

class EmergencyEventCreate(BaseModel):
    trigger_id: UUID | None = None
    source_message_id: UUID | None = None
    detected_symptoms: list[Any] = Field(default_factory=list)
    alert_message: str

class ConversationSummaryOut(BaseModel):
    session_id: UUID
    language: LanguageCode
    status: SessionStatus
    started_at: datetime
    ended_at: datetime | None = None
    severity: SeverityLevel | None = None
    department_name_en: str | None = None
    department_name_th: str | None = None
    message_count: int