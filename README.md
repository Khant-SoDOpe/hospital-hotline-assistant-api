# AI OPD Pre-Screening and Triage API

FastAPI backend for an AI-assisted OPD pre-screening workflow. The API supports patient symptom intake, guided questioning, urgency classification, OPD recommendation, nurse review, appointment handling, routing feedback, user/department administration, audit logs, and analytics.

The system stores assessment information and workflow decisions only. It does not diagnose disease, prescribe medication, or replace healthcare professionals.

## Setup

1. Create and activate a virtual environment.
2. Install dependencies: `pip install -r requirements.txt`.
3. Copy `.env.example` to `.env` and update `DATABASE_URL`.
4. Create the database: `createdb -h localhost -U postgres hospital_hotline`.
5. Run the migrations in order:

```bash
psql "$DATABASE_URL" -f migrations/001_hospital_hotline_schema.sql
psql "$DATABASE_URL" -f migrations/002_ai_opd_triage_srs_update.sql
```

6. Start the API:

```bash
uvicorn app.main:app --reload
```

Interactive docs are available at `http://localhost:8000/docs`.

## Main Workflow

1. Patient starts an assessment with `POST /sessions`.
2. Patient submits text or voice messages with `POST /sessions/{session_id}/messages`.
3. AI or app stores extracted symptoms with `POST /sessions/{session_id}/symptoms`.
4. AI stores guided questions with `POST /sessions/{session_id}/follow-up-questions`.
5. AI stores final assessment output with `POST /sessions/{session_id}/assessment-results`.
6. Nurse reviews pending results from `GET /nurse/assessment-results?status=pending_review`.
7. Nurse approves, modifies, or rejects with the assessment action endpoints.
8. Patient requests an appointment with `POST /sessions/{session_id}/appointment-requests`.
9. Nurse confirms or suggests alternatives from the appointment endpoints.

## Endpoint Groups

Health and docs:
- `GET /`
- `GET /health`
- `GET /docs`

Patient assessment:
- `POST /sessions`
- `GET /sessions/{session_id}`
- `PATCH /sessions/{session_id}`
- `POST /sessions/{session_id}/messages`
- `GET /sessions/{session_id}/messages`
- `GET /sessions/{session_id}/context`
- `POST /sessions/{session_id}/symptoms`
- `GET /sessions/{session_id}/symptoms`
- `POST /sessions/{session_id}/follow-up-questions`
- `GET /sessions/{session_id}/follow-up-questions`
- `PATCH /follow-up-questions/{question_id}/answer`
- `POST /sessions/{session_id}/severity-assessments`
- `GET /sessions/{session_id}/severity-assessments`
- `POST /sessions/{session_id}/department-recommendations`
- `GET /sessions/{session_id}/department-recommendations`
- `POST /sessions/{session_id}/assessment-results`
- `GET /sessions/{session_id}/assessment-results`
- `GET /assessment-results/{assessment_result_id}`

Nurse review:
- `GET /nurse/assessment-results`
- `POST /assessment-results/{assessment_result_id}/approve`
- `POST /assessment-results/{assessment_result_id}/modify`
- `POST /assessment-results/{assessment_result_id}/reject`
- `PATCH /departments/{department_id}/availability`
- `POST /assessment-results/{assessment_result_id}/routing-feedback`
- `GET /routing-feedback`

Appointments:
- `POST /sessions/{session_id}/appointment-requests`
- `GET /sessions/{session_id}/appointment-requests`
- `GET /appointment-requests`
- `GET /appointment-requests/{appointment_id}`
- `POST /appointment-requests/{appointment_id}/confirm`
- `POST /appointment-requests/{appointment_id}/suggest-alternatives`
- `PATCH /appointment-requests/{appointment_id}`

Administration:
- `POST /users`
- `GET /users`
- `GET /users/{user_id}`
- `PATCH /users/{user_id}`
- `DELETE /users/{user_id}`
- `POST /departments`
- `GET /departments`
- `GET /departments/{department_id}`
- `PATCH /departments/{department_id}`
- `DELETE /departments/{department_id}`
- `POST /routing-rules`
- `GET /routing-rules`
- `GET /routing-rules/{rule_id}`
- `PATCH /routing-rules/{rule_id}`
- `DELETE /routing-rules/{rule_id}`
- `POST /emergency-triggers`
- `GET /emergency-triggers`
- `GET /emergency-triggers/{trigger_id}`
- `PATCH /emergency-triggers/{trigger_id}`
- `DELETE /emergency-triggers/{trigger_id}`

Analytics and records:
- `GET /analytics/summary`
- `GET /analytics/assessment-summary`
- `GET /audit-logs`
- `GET /conversation-summary`

## Notes

- Use `assessment_results.urgency` for SRS urgency values: `high`, `medium`, `low`, or `unknown`.
- The older `severity_assessments` endpoints are still available for compatibility with the original MVP schema.
- Deploy behind HTTPS in production to meet the SRS communication requirement.
- If `.env` sets `APP_NAME`, it overrides the default title in `app/config.py`.
