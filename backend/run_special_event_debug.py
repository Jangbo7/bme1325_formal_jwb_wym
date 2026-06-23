from __future__ import annotations

import argparse
import json
import os
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.api.contract import ContractError
from app.config import get_settings
from app.database import Database
from app.main import create_container


ESCALATION_EVENTS = {"emergency_escalation", "icu_escalation"}
STEP_SESSION_LIMIT = 200


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a single intelligent_agent special-event patient end-to-end and dump a debug report.",
    )
    parser.add_argument(
        "--event",
        required=True,
        choices=["emergency_escalation", "icu_escalation", "specialty_referral"],
        help="Rare event type to search for and debug.",
    )
    parser.add_argument(
        "--department",
        default="internal",
        help="Generation hint department_id, for example internal or surgery.",
    )
    parser.add_argument(
        "--seed",
        default="",
        help="Optional exact seed. If omitted, the script searches for a matching seed.",
    )
    parser.add_argument(
        "--seed-prefix",
        default="special-event-debug",
        help="Prefix used when searching seeds automatically.",
    )
    parser.add_argument(
        "--max-seed-search",
        type=int,
        default=400,
        help="Maximum number of candidate seeds to inspect when --seed is omitted.",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=32,
        help="Maximum runner steps before the script stops.",
    )
    parser.add_argument(
        "--db-path",
        default="",
        help="Optional sqlite database file path. Defaults to an isolated temp db under backend/_tmp_special_event_debug.",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Optional JSON report path. Defaults to backend/_tmp_special_event_debug/<timestamp>-<event>.json",
    )
    return parser.parse_args()


def ensure_debug_environment(args: argparse.Namespace) -> tuple[Path, Path]:
    debug_dir = BACKEND_DIR / "_tmp_special_event_debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    db_path = Path(args.db_path).expanduser() if args.db_path else debug_dir / f"{timestamp}-{args.event}.db"
    output_path = Path(args.output).expanduser() if args.output else debug_dir / f"{timestamp}-{args.event}.json"
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ["SIMULATOR_ENABLED"] = "false"
    os.environ["REDIS_MIRROR_ENABLED"] = "false"
    os.environ.setdefault("RESET_ON_SERVER_START", "true")
    return db_path, output_path


def decode_json_value(value):
    if isinstance(value, (dict, list)):
        return deepcopy(value)
    if value in (None, ""):
        return {}
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return value
    return value


def sanitize_patient_row(row: dict | None) -> dict | None:
    if not row:
        return None
    return {
        "id": row.get("id"),
        "name": row.get("name"),
        "lifecycle_state": row.get("lifecycle_state"),
        "location": row.get("location"),
        "visit_id": row.get("visit_id"),
        "session_id": row.get("session_id"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def sanitize_visit_row(row: dict | None) -> dict | None:
    if not row:
        return None
    return {
        "id": row.get("id"),
        "state": row.get("state"),
        "assigned_department_id": row.get("assigned_department_id"),
        "assigned_department_name": row.get("assigned_department_name"),
        "current_node": row.get("current_node"),
        "current_department": row.get("current_department"),
        "active_agent_type": row.get("active_agent_type"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "data": decode_json_value(row.get("data_json")),
    }


def session_agent_pairs(visit_data: dict, state) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    known_keys = {
        "triage_session_id": "triage",
        "internal_medicine_session_id": "internal_medicine",
        "internal_medicine_round2_session_id": "internal_medicine",
        "surgery_session_id": "surgery",
        "surgery_round2_session_id": "surgery",
    }
    for key, agent_type in known_keys.items():
        session_id = str(visit_data.get(key) or "").strip()
        if session_id:
            pairs.append((session_id, agent_type))
    if state.active_session_id:
        active_session_id = str(state.active_session_id).strip()
        if active_session_id and all(active_session_id != item[0] for item in pairs):
            guessed_agent = str(state.current_counterparty or "").replace("_agent", "").strip() or "unknown"
            pairs.append((active_session_id, guessed_agent))
    deduped: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for pair in pairs:
        if pair not in seen:
            deduped.append(pair)
            seen.add(pair)
    return deduped


def collect_sessions(container: dict, visit_id: str | None, visit_data: dict, state) -> list[dict]:
    if not visit_id:
        return []
    session_repo = container["session_repo"]
    memory_repo = container["memory_repo"]
    sessions: list[dict] = []
    for session_id, agent_type in session_agent_pairs(visit_data, state):
        session_row = session_repo.get(session_id)
        if not session_row:
            continue
        patient_id = str(session_row.get("patient_id") or state.patient_id)
        private_memory = memory_repo.peek_agent_session_memory(session_id, agent_type)
        if private_memory is None:
            try:
                private_memory = memory_repo.get_agent_session_memory(session_id, patient_id, agent_type=agent_type)
            except Exception as exc:
                private_memory = {"error": str(exc)}
        sessions.append(
            {
                "session_id": session_id,
                "agent_type": agent_type,
                "dialogue_state": session_row.get("dialogue_state"),
                "created_at": session_row.get("created_at"),
                "updated_at": session_row.get("updated_at"),
                "private_memory": deepcopy(private_memory),
                "turns": session_repo.list_turns(session_id, limit=STEP_SESSION_LIMIT),
            }
        )
    return sessions


def collect_step_snapshot(container: dict, state, *, index: int, note: str) -> dict:
    patient_repo = container["patient_repo"]
    visit_repo = container["visit_repo"]
    memory_repo = container["memory_repo"]
    case_repo = container["patient_agent_case_repo"]
    medical_record_repo = container["medical_record_repo"]

    patient_row = patient_repo.get(state.patient_id)
    visit_row = visit_repo.get(state.encounter_id) if state.encounter_id else None
    visit_view = sanitize_visit_row(visit_row)
    visit_data = dict((visit_view or {}).get("data") or {})
    case_row = case_repo.get_latest_by_visit(state.encounter_id, mode="intelligent_agent") if state.encounter_id else None
    case_payload = decode_json_value((case_row or {}).get("case_json"))
    shared_memory = memory_repo.get_shared_memory(
        state.patient_id,
        ((state.case_summary or {}).get("name") or state.patient_id),
    )
    sessions = collect_sessions(container, state.encounter_id, visit_data, state)
    timeline = medical_record_repo.get_visit_timeline(state.encounter_id) if medical_record_repo and state.encounter_id else None

    return {
        "index": index,
        "captured_at": now_iso(),
        "note": note,
        "snapshot": state.to_snapshot().model_dump(),
        "patient": sanitize_patient_row(patient_row),
        "visit": visit_view,
        "case_row": {
            "id": (case_row or {}).get("id"),
            "status": (case_row or {}).get("status"),
            "mode": (case_row or {}).get("mode"),
            "created_at": (case_row or {}).get("created_at"),
            "updated_at": (case_row or {}).get("updated_at"),
            "case_payload": case_payload,
        },
        "shared_memory": shared_memory,
        "sessions": sessions,
        "medical_record_timeline": timeline,
    }


def choose_seed(container: dict, args: argparse.Namespace) -> tuple[str, dict, list[dict]]:
    generator = container["patient_agent_service"].agent.case_generator
    inspected: list[dict] = []
    if args.seed:
        profile = generator._sample_rare_event_profile(seed=args.seed, department_id=args.department)
        inspected.append({"seed": args.seed, "profile": profile.model_dump()})
        return args.seed, profile.model_dump(), inspected

    for index in range(args.max_seed_search):
        seed = f"{args.seed_prefix}-{args.department}-{args.event}-{index:04d}"
        profile = generator._sample_rare_event_profile(seed=seed, department_id=args.department)
        inspected.append({"seed": seed, "profile": profile.model_dump()})
        if profile.event_type == args.event:
            return seed, profile.model_dump(), inspected
    raise RuntimeError(
        f"Unable to find a seed for event={args.event} department={args.department} within {args.max_seed_search} attempts."
    )


def build_analysis(report: dict, desired_event: str) -> dict:
    findings: list[str] = []
    milestones: list[dict] = []
    steps = list(report.get("steps") or [])
    for step in steps:
        snapshot = step.get("snapshot") or {}
        visit = step.get("visit") or {}
        visit_data = dict(visit.get("data") or {})
        simulated_report = dict(visit_data.get("simulated_report") or {})
        report_summary = dict(simulated_report.get("report_summary") or {})
        milestone = {
            "index": step.get("index"),
            "visit_state": snapshot.get("visit_state"),
            "phase": snapshot.get("phase"),
            "last_action": snapshot.get("last_action"),
            "primary_disposition": snapshot.get("primary_disposition"),
            "disposition_category": (snapshot.get("disposition") or {}).get("category"),
            "report_acuity_level": report_summary.get("acuity_level"),
            "report_escalation_clues": report_summary.get("escalation_clues"),
        }
        milestones.append(milestone)

    spawn_profile = dict((report.get("spawn") or {}).get("rare_event_profile") or {})
    final_step = steps[-1] if steps else {}
    final_snapshot = dict(final_step.get("snapshot") or {})
    final_disposition = dict(final_snapshot.get("disposition") or {})
    final_category = str(final_disposition.get("category") or "")
    final_primary = str(final_snapshot.get("primary_disposition") or "")

    if spawn_profile.get("event_type") != desired_event:
        findings.append(
            f"Seed/profile mismatch: sampled event_type={spawn_profile.get('event_type')} but desired_event={desired_event}."
        )

    report_steps = [
        step for step in steps
        if isinstance(((step.get("visit") or {}).get("data") or {}).get("simulated_report"), dict)
    ]
    first_report_step = report_steps[0] if report_steps else None
    if desired_event in ESCALATION_EVENTS:
        if not first_report_step:
            findings.append("No simulated_report was generated before the flow ended, so report-layer escalation never had a chance to trigger.")
        else:
            report_summary = dict((((first_report_step.get("visit") or {}).get("data") or {}).get("simulated_report") or {}).get("report_summary") or {})
            escalation_clues = dict(report_summary.get("escalation_clues") or {})
            if desired_event == "emergency_escalation" and not escalation_clues.get("to_emergency"):
                findings.append(
                    "The flow generated a simulated report, but escalation_clues.to_emergency was still false at the first report step."
                )
            if desired_event == "icu_escalation" and not escalation_clues.get("to_icu"):
                findings.append(
                    "The flow generated a simulated report, but escalation_clues.to_icu was still false at the first report step."
                )

    if desired_event == "emergency_escalation":
        if final_primary != "emergency_escalation" and final_category != "emergency_escalation":
            findings.append(
                f"Final flow did not materialize as emergency escalation: primary_disposition={final_primary or '-'}, category={final_category or '-'}."
            )
    elif desired_event == "icu_escalation":
        if final_primary != "icu_escalation" and final_category != "icu_rescue":
            findings.append(
                f"Final flow did not materialize as ICU escalation: primary_disposition={final_primary or '-'}, category={final_category or '-'}."
            )
    elif desired_event == "specialty_referral":
        if final_primary != "specialty_referral" and final_category != "specialty_referral":
            findings.append(
                f"Final flow did not materialize as specialty referral: primary_disposition={final_primary or '-'}, category={final_category or '-'}."
            )

    if not findings:
        findings.append("No structural mismatch detected in this run.")

    return {
        "findings": findings,
        "milestones": milestones,
        "final_primary_disposition": final_primary or None,
        "final_disposition_category": final_category or None,
        "finished": bool(final_snapshot.get("finished")),
        "step_count": len(steps),
    }


def write_report(output_path: Path, report: dict) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    args = parse_args()
    db_path, output_path = ensure_debug_environment(args)
    started_at = now_iso()
    settings = get_settings()
    container = create_container()
    controller = container["patient_agent_debug_controller"]
    runner = controller.runner

    report = {
        "meta": {
            "started_at": started_at,
            "db_path": str(db_path),
            "output_path": str(output_path),
            "llm_provider": settings.get("active_llm_provider"),
            "llm_model": settings.get("llm_model"),
            "llm_endpoint": settings.get("llm_endpoint"),
            "department": args.department,
            "desired_event": args.event,
            "max_steps": args.max_steps,
            "max_seed_search": args.max_seed_search,
        },
        "seed_search": {},
        "spawn": {},
        "steps": [],
        "analysis": {},
        "error": None,
    }

    try:
        chosen_seed, sampled_profile, inspected = choose_seed(container, args)
        report["seed_search"] = {
            "chosen_seed": chosen_seed,
            "inspected_count": len(inspected),
            "sampled_profile": sampled_profile,
            "inspected_preview": inspected[:25],
        }
        print(f"[seed] chosen={chosen_seed} event={sampled_profile.get('event_type')} department={args.department}")

        state = runner.spawn(seed=chosen_seed, department_id=args.department)
        report["spawn"] = {
            "seed": chosen_seed,
            "department": args.department,
            "rare_event_profile": dict(state.rare_event_profile),
            "snapshot": state.to_snapshot().model_dump(),
        }
        report["steps"].append(collect_step_snapshot(container, state, index=0, note="spawn"))
        print(
            f"[spawn] patient={state.patient_id} visit={state.encounter_id} "
            f"rare_event={state.rare_event_type}/{state.rare_event_triggered_by}"
        )

        for step_index in range(1, args.max_steps + 1):
            before_state = state.to_snapshot().model_dump()
            print(
                f"[step:{step_index}] before phase={before_state.get('phase')} "
                f"visit_state={before_state.get('visit_state')} action={before_state.get('last_action')}"
            )
            runner.step(state)
            after_state = state.to_snapshot().model_dump()
            print(
                f"[step:{step_index}] after phase={after_state.get('phase')} "
                f"visit_state={after_state.get('visit_state')} disposition={after_state.get('primary_disposition') or '-'} "
                f"finished={after_state.get('finished')}"
            )
            report["steps"].append(collect_step_snapshot(container, state, index=step_index, note="post_step"))
            if state.finished:
                break

        report["analysis"] = build_analysis(report, args.event)
        write_report(output_path, report)

        print("[analysis]")
        for finding in report["analysis"]["findings"]:
            print(f" - {finding}")
        print(f"[report] {output_path}")
        return 0
    except ContractError as exc:
        report["error"] = {
            "type": "ContractError",
            "code": exc.code,
            "message": exc.message,
            "details": exc.details,
        }
    except Exception as exc:
        report["error"] = {
            "type": type(exc).__name__,
            "message": str(exc),
        }
    finally:
        report["meta"]["finished_at"] = now_iso()
        report["analysis"] = report["analysis"] or build_analysis(report, args.event)
        write_report(output_path, report)
        shutdown = container.get("multi_patient_debug_controller")
        if shutdown is not None:
            try:
                shutdown.shutdown()
            except Exception:
                pass

    print("[error]")
    print(json.dumps(report["error"], ensure_ascii=False, indent=2))
    print(f"[report] {output_path}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
