from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

LanguageCode = Literal["th", "en"]
SessionStatus = Literal["active", "completed", "reset", "escalated"]
MessageRole = Literal["user", "assistant", "system"]
InputMode = Literal["voice", "text"]
SeverityLevel = Literal["emergency", "urgent", "general", "unknown"]

UserRole = Literal["patient", "opd_nurse", "administrator"]
UrgencyLevel = Literal["high", "medium", "low", "unknown"]
AssessmentStatus = Literal["pending_review", "approved", "modified", "rejected"]
AppointmentStatus = Literal[
    "pending",
    "confirmed",
    "alternative_suggested",
    "cancelled",
    "rejected",
]
DepartmentAvailabilityStatus = Literal["available", "limited", "unavailable"]


class UserCreate(BaseModel):
    role: UserRole = "patient"
    email: str | None = None
    phone: str | None = None
    full_name: str | None = None
    is_active: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class UserUpdate(BaseModel):
    role: UserRole | None = None
    email: str | None = None
    phone: str | None = None
    full_name: str | None = None
    is_active: bool | None = None
    metadata: dict[str, Any] | None = None


class UserOut(BaseModel):
    id: UUID
    role: UserRole
    email: str | None = None
    phone: str | None = None
    full_name: str | None = None
    is_active: bool
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class SessionCreate(BaseModel):
    language: LanguageCode = "th"
    patient_user_id: UUID | None = None
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
    patient_user_id: UUID | None = None
    user_agent: str | None = None
    ip_hash: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


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


class SymptomEntryOut(SymptomEntryCreate):
    id: UUID
    session_id: UUID
    created_at: datetime


class FollowUpQuestionCreate(BaseModel):
    question_text: str
    reason: str | None = None


class FollowUpQuestionAnswer(BaseModel):
    answer_message_id: UUID


class FollowUpQuestionOut(BaseModel):
    id: UUID
    session_id: UUID
    question_text: str
    reason: str | None = None
    asked_at: datetime
    answer_message_id: UUID | None = None
    answered_at: datetime | None = None


class SeverityAssessmentCreate(BaseModel):
    source_message_id: UUID | None = None
    severity: SeverityLevel = "unknown"
    confidence: float | None = Field(default=None, ge=0, le=1)
    explanation: str | None = None
    detected_triggers: list[Any] = Field(default_factory=list)


class SeverityAssessmentOut(SeverityAssessmentCreate):
    id: UUID
    session_id: UUID
    created_at: datetime


class DepartmentCreate(BaseModel):
    code: str
    name_en: str
    name_th: str | None = None
    description_en: str | None = None
    description_th: str | None = None
    is_active: bool = True
    availability_status: DepartmentAvailabilityStatus = "available"
    accepting_appointments: bool = True
    unavailable_reason: str | None = None
    next_available_date: date | None = None
    capacity_per_day: int | None = Field(default=None, ge=0)


class DepartmentUpdate(BaseModel):
    code: str | None = None
    name_en: str | None = None
    name_th: str | None = None
    description_en: str | None = None
    description_th: str | None = None
    is_active: bool | None = None
    availability_status: DepartmentAvailabilityStatus | None = None
    accepting_appointments: bool | None = None
    unavailable_reason: str | None = None
    next_available_date: date | None = None
    capacity_per_day: int | None = Field(default=None, ge=0)


class DepartmentAvailabilityUpdate(BaseModel):
    availability_status: DepartmentAvailabilityStatus
    accepting_appointments: bool | None = None
    unavailable_reason: str | None = None
    next_available_date: date | None = None
    capacity_per_day: int | None = Field(default=None, ge=0)


class DepartmentOut(BaseModel):
    id: UUID
    code: str
    name_en: str
    name_th: str | None = None
    description_en: str | None = None
    description_th: str | None = None
    is_active: bool
    availability_status: DepartmentAvailabilityStatus = "available"
    accepting_appointments: bool = True
    unavailable_reason: str | None = None
    next_available_date: date | None = None
    capacity_per_day: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class RoutingRuleCreate(BaseModel):
    department_id: UUID
    rule_name: str
    description: str | None = None
    symptom_keywords: list[str] = Field(default_factory=list)
    condition_json: dict[str, Any] = Field(default_factory=dict)
    severity_override: SeverityLevel | None = None
    priority: int = 100
    is_active: bool = True
    created_by: UUID | None = None
    updated_by: UUID | None = None


class RoutingRuleUpdate(BaseModel):
    department_id: UUID | None = None
    rule_name: str | None = None
    description: str | None = None
    symptom_keywords: list[str] | None = None
    condition_json: dict[str, Any] | None = None
    severity_override: SeverityLevel | None = None
    priority: int | None = None
    is_active: bool | None = None
    updated_by: UUID | None = None


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
    created_by: UUID | None = None
    updated_by: UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class EmergencyTriggerCreate(BaseModel):
    trigger_name: str
    description: str | None = None
    trigger_keywords: list[str] = Field(default_factory=list)
    condition_json: dict[str, Any] = Field(default_factory=dict)
    alert_message_en: str
    alert_message_th: str | None = None
    priority: int = 1
    is_active: bool = True
    created_by: UUID | None = None
    updated_by: UUID | None = None


class EmergencyTriggerUpdate(BaseModel):
    trigger_name: str | None = None
    description: str | None = None
    trigger_keywords: list[str] | None = None
    condition_json: dict[str, Any] | None = None
    alert_message_en: str | None = None
    alert_message_th: str | None = None
    priority: int | None = None
    is_active: bool | None = None
    updated_by: UUID | None = None


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
    created_by: UUID | None = None
    updated_by: UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DepartmentRecommendationCreate(BaseModel):
    assessment_id: UUID | None = None
    department_id: UUID
    confidence: float | None = Field(default=None, ge=0, le=1)
    reason: str | None = None


class DepartmentRecommendationOut(DepartmentRecommendationCreate):
    id: UUID
    session_id: UUID
    created_at: datetime


class EmergencyEventCreate(BaseModel):
    trigger_id: UUID | None = None
    source_message_id: UUID | None = None
    detected_symptoms: list[Any] = Field(default_factory=list)
    alert_message: str


class EmergencyEventOut(EmergencyEventCreate):
    id: UUID
    session_id: UUID
    created_at: datetime


class AssessmentResultCreate(BaseModel):
    source_assessment_id: UUID | None = None
    recommendation_id: UUID | None = None
    summary: str
    urgency: UrgencyLevel = "unknown"
    department_id: UUID | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    ai_metadata: dict[str, Any] = Field(default_factory=dict)


class AssessmentResultUpdate(BaseModel):
    summary: str | None = None
    urgency: UrgencyLevel | None = None
    department_id: UUID | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    ai_metadata: dict[str, Any] | None = None
    status: AssessmentStatus | None = None


class AssessmentApprove(BaseModel):
    nurse_user_id: UUID | None = None
    nurse_notes: str | None = None


class AssessmentModify(BaseModel):
    nurse_user_id: UUID | None = None
    final_urgency: UrgencyLevel
    final_department_id: UUID | None = None
    nurse_notes: str | None = None


class AssessmentReject(BaseModel):
    nurse_user_id: UUID | None = None
    rejection_reason: str
    nurse_notes: str | None = None


class AssessmentResultOut(BaseModel):
    id: UUID
    session_id: UUID
    source_assessment_id: UUID | None = None
    recommendation_id: UUID | None = None
    summary: str
    urgency: UrgencyLevel
    department_id: UUID | None = None
    confidence: float | None = None
    ai_metadata: dict[str, Any] = Field(default_factory=dict)
    status: AssessmentStatus
    final_urgency: UrgencyLevel | None = None
    final_department_id: UUID | None = None
    nurse_user_id: UUID | None = None
    nurse_notes: str | None = None
    rejection_reason: str | None = None
    reviewed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class AppointmentRequestCreate(BaseModel):
    assessment_result_id: UUID | None = None
    patient_user_id: UUID | None = None
    department_id: UUID | None = None
    requested_date: date | None = None
    requested_time: str | None = None
    reason: str | None = None


class AppointmentConfirm(BaseModel):
    nurse_user_id: UUID | None = None
    confirmed_date: date
    confirmed_time: str | None = None
    nurse_notes: str | None = None


class AppointmentSuggestAlternatives(BaseModel):
    nurse_user_id: UUID | None = None
    alternative_dates: list[date]
    nurse_notes: str | None = None


class AppointmentStatusUpdate(BaseModel):
    status: AppointmentStatus
    nurse_user_id: UUID | None = None
    nurse_notes: str | None = None


class AppointmentRequestOut(BaseModel):
    id: UUID
    session_id: UUID
    assessment_result_id: UUID | None = None
    patient_user_id: UUID | None = None
    department_id: UUID | None = None
    requested_date: date | None = None
    requested_time: str | None = None
    reason: str | None = None
    status: AppointmentStatus
    confirmed_date: date | None = None
    confirmed_time: str | None = None
    alternative_dates: list[Any] = Field(default_factory=list)
    nurse_user_id: UUID | None = None
    nurse_notes: str | None = None
    created_at: datetime
    updated_at: datetime


class RoutingFeedbackCreate(BaseModel):
    nurse_user_id: UUID | None = None
    original_department_id: UUID | None = None
    corrected_department_id: UUID | None = None
    original_urgency: UrgencyLevel | None = None
    corrected_urgency: UrgencyLevel | None = None
    feedback_text: str


class RoutingFeedbackOut(RoutingFeedbackCreate):
    id: UUID
    assessment_result_id: UUID | None = None
    session_id: UUID
    created_at: datetime


class AnalyticsSummaryOut(BaseModel):
    total_sessions: int
    total_assessment_results: int
    pending_reviews: int
    approved_reviews: int
    modified_reviews: int
    rejected_reviews: int
    total_appointments: int
    pending_appointments: int
    confirmed_appointments: int
    urgency_distribution: dict[str, int]
    department_distribution: dict[str, int]


class AuditLogOut(BaseModel):
    id: UUID
    admin_user_id: UUID | None = None
    actor_user_id: UUID | None = None
    action: str
    entity_type: str
    entity_id: UUID | None = None
    before_data: dict[str, Any] | None = None
    after_data: dict[str, Any] | None = None
    created_at: datetime


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
