import os, json, time, sqlite3, uuid, threading, sys
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from fastapi.testclient import TestClient
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.main import create_app

sample_every = float(os.environ.get('SAMPLE_EVERY', '2'))
duration = float(os.environ.get('SCENARIO_DURATION', '30'))
mode = os.environ.get('SCENARIO_MODE', 'intelligent_agent')
max_active = int(os.environ.get('SCENARIO_MAX_ACTIVE', '2'))
step_interval = float(os.environ.get('SCENARIO_STEP_INTERVAL', '0.2'))
spawn_interval = float(os.environ.get('SCENARIO_SPAWN_INTERVAL', '0'))
label = os.environ.get('SCENARIO_LABEL', 'unnamed')
slow_llm_port = os.environ.get('SLOW_LLM_PORT', '').strip()

if slow_llm_port:
    class SlowHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get('Content-Length', '0') or '0')
            if length:
                self.rfile.read(length)
            time.sleep(22)
            body = json.dumps({'choices':[{'message':{'content':'{}'}}]}).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, format, *args):
            return
    server = ThreadingHTTPServer(('127.0.0.1', int(slow_llm_port)), SlowHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
else:
    server = None

app = create_app()
client = TestClient(app)
headers = {'X-API-Key': 'mock-key-001'}

def db_path_from_url(url: str) -> Path:
    rel = url.replace('sqlite:///', '', 1)
    p = Path(rel)
    if not p.is_absolute():
        p = Path.cwd() / rel
    return p

def grouped_dict(rows, key_builder):
    out = {}
    for r in rows:
        out[key_builder(r)] = r['c']
    return out

def db_snapshot(db_path: Path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    out = {}
    out['visits_by_state'] = grouped_dict(conn.execute("select state, count(*) c from visits group by state").fetchall(), lambda r: str(r['state']))
    out['queue_by_status_kind'] = grouped_dict(conn.execute("select status, queue_kind, count(*) c from queue_tickets group by status, queue_kind").fetchall(), lambda r: f"{r['status']}|{r['queue_kind']}")
    out['runtime_by_flow'] = grouped_dict(conn.execute("select department_flow_status, count(*) c from department_patient_runtime group by department_flow_status").fetchall(), lambda r: str(r['department_flow_status']))
    out['session_turns'] = conn.execute("select count(*) from session_turns").fetchone()[0]
    out['agent_session_memory'] = conn.execute("select count(*) from agent_session_memory").fetchone()[0]
    response_source = {}
    llm_errors = {}
    for row in conn.execute("select session_id, agent_type, data_json from agent_session_memory"):
        try:
            data = json.loads(row['data_json'])
        except Exception:
            continue
        diag = data.get('llm_diagnostics') or {}
        src = diag.get('response_source')
        if src:
            response_source[src] = response_source.get(src, 0) + 1
        err = diag.get('llm_error')
        if err:
            llm_errors[err] = llm_errors.get(err, 0) + 1
    out['consult_response_source'] = response_source
    out['consult_llm_errors'] = llm_errors
    conn.close()
    return out

health = client.get('/api/v1/health', headers=headers).json()['data']
start = client.post('/api/v1/multi-patient-debug/start', headers={**headers, 'Idempotency-Key': str(uuid.uuid4())}, json={
    'mode': mode,
    'spawn_interval_seconds': spawn_interval,
    'step_interval_seconds': step_interval,
    'max_active_patients': max_active,
})
start_payload = start.json()
settings = app.state.container['settings']
db_path = db_path_from_url(settings['database_url'])

samples = []
last_signature = None
stall_ticks = 0
max_stall_ticks = 0
last_tick_value = None
last_tick_unchanged_ticks = 0
max_last_tick_unchanged_ticks = 0
iterations = int(duration // sample_every)
for i in range(iterations + 1):
    snap = client.get('/api/v1/multi-patient-debug/snapshot', headers=headers).json()['data']
    hsnap = client.get('/api/v1/hospital-runtime-debug/snapshot', headers=headers).json()['data']
    dbs = db_snapshot(db_path)
    patients = snap.get('patients', [])
    signature = [
        (p['npc_id'], p['step_count'], p['phase'], p['status'], p.get('visit_state'), p.get('last_action'), p.get('last_error'))
        for p in patients
    ]
    stall_ticks = stall_ticks + 1 if signature == last_signature else 0
    max_stall_ticks = max(max_stall_ticks, stall_ticks)
    last_signature = signature
    tick = snap.get('last_tick_at')
    last_tick_unchanged_ticks = last_tick_unchanged_ticks + 1 if tick == last_tick_value else 0
    max_last_tick_unchanged_ticks = max(max_last_tick_unchanged_ticks, last_tick_unchanged_ticks)
    last_tick_value = tick
    waiting_capacity = [p['npc_id'] for p in patients if p.get('status') == 'waiting_capacity' or (p.get('last_error') or '').startswith('node capacity reached:')]
    sample = {
        't': int(i * sample_every),
        'active_count': snap['active_count'],
        'spawned': snap['total_spawned'],
        'dispatch': snap['dispatch_count'],
        'blocked': snap['blocked_count'],
        'currently_blocked': hsnap.get('currently_blocked_patients', 0),
        'last_tick_at': tick,
        'waiting_capacity': waiting_capacity,
        'patients': [
            {
                'npc_id': p['npc_id'],
                'dept': p.get('assigned_department_id'),
                'src': p.get('patient_source'),
                'step_count': p['step_count'],
                'phase': p['phase'],
                'status': p['status'],
                'visit_state': p.get('visit_state'),
                'last_action': p.get('last_action'),
                'last_error': p.get('last_error'),
            }
            for p in patients
        ],
        'db': dbs,
        'stall_ticks': stall_ticks,
        'last_tick_unchanged_ticks': last_tick_unchanged_ticks,
    }
    samples.append(sample)
    time.sleep(sample_every)

client.post('/api/v1/multi-patient-debug/stop', headers={**headers, 'Idempotency-Key': str(uuid.uuid4())})
client.post('/api/v1/multi-patient-debug/reset', headers={**headers, 'Idempotency-Key': str(uuid.uuid4())})
if server is not None:
    server.shutdown()

final = samples[-1] if samples else {}
all_patients = {}
for s in samples:
    for p in s['patients']:
        all_patients[p['npc_id']] = p
summary = {
    'label': label,
    'health': health,
    'start_ok': start.status_code == 200 and bool(start_payload.get('ok')),
    'start_error': start_payload.get('error'),
    'max_active_count': max((s['active_count'] for s in samples), default=0),
    'max_spawned': max((s['spawned'] for s in samples), default=0),
    'max_blocked_count': max((s['blocked'] for s in samples), default=0),
    'max_waiting_capacity_patients': max((len(s['waiting_capacity']) for s in samples), default=0),
    'max_signature_stall_seconds': max_stall_ticks * sample_every,
    'max_last_tick_unchanged_seconds': max_last_tick_unchanged_ticks * sample_every,
    'final_consult_response_source': final.get('db', {}).get('consult_response_source', {}),
    'final_consult_llm_errors': final.get('db', {}).get('consult_llm_errors', {}),
    'final_visits_by_state': final.get('db', {}).get('visits_by_state', {}),
    'final_runtime_by_flow': final.get('db', {}).get('runtime_by_flow', {}),
    'final_session_turns': final.get('db', {}).get('session_turns', 0),
    'final_agent_session_memory': final.get('db', {}).get('agent_session_memory', 0),
    'final_patients': list(all_patients.values()),
    'sample_first': samples[0] if samples else None,
    'sample_mid': samples[len(samples)//2] if samples else None,
    'sample_last': final,
    'first_waiting_capacity_sample': next((s for s in samples if s['waiting_capacity']), None),
    'first_llm_error_sample': next((s for s in samples if s.get('db', {}).get('consult_llm_errors')), None),
}
print(json.dumps(summary, ensure_ascii=False))
