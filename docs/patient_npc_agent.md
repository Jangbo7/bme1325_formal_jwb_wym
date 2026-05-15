# Task: Implement a controlled simulated patient agent with case generation, dialogue policy, and optional RAG-style constraints

## Background

This project is a simulated hospital triage and queue system. It already has a backend orchestration layer based on FastAPI and a session/event-bus style architecture. We have partially implemented patient agents, but we have not yet added concrete RAG-style constraints or output control.

The goal is to implement a simulated patient agent that can:

1. Autonomously generate a common, simple initial symptom / chief complaint.
2. Interact with a triage or consultation agent.
3. Answer intelligently according to the triage/doctor agent's questions.
4. Ask reasonable follow-up questions when appropriate.
5. Stay consistent with its generated patient case.
6. Avoid acting like a doctor or revealing hidden diagnosis labels directly.

This implementation should be modular, minimal, and easy to extend.

---

## Core Design Principle

Do not implement a fully open-ended medical chatbot.

Implement a controlled simulated patient agent.

The patient agent should be grounded by a structured `PatientCaseCard`. The `PatientCaseCard` is the main source of truth for the patient's symptoms, background, communication style, and hidden internal diagnosis hint.

The agent may use RAG-style retrieval later, but in this phase, prioritize structured case constraints and prompt-level guardrails.

---

## Required Modules

Please add or update the following modules. Use the existing project structure when possible.

Suggested new files:

```text
backend/app/agents/patient_agent/
  __init__.py
  schemas.py
  case_generator.py
  patient_policy.py
  patient_agent.py
  prompt_builder.py
  rag_context.py
  examples.py

backend/app/services/
  patient_agent_service.py

backend/app/tests/
  test_patient_case_generator.py
  test_patient_agent_policy.py
  test_patient_agent_dialogue.py