### phase1(Synchronous modification of frontend and backend):
First，Realize the standardized transformation of the entire outpatient process, and unify it into the orchestration layer while defining the state event guard table：
The process is as follows：
The outpatient process usually starts with triage.And then registration . 
After registration, the patient goes to the assigned floor, department, and triage desk according to the registration slip. The patient then waits in the designated waiting area until called.
The first major medical step is the initial doctor consultation. During this consultation, the doctor asks about the patient’s symptoms, medical history, medication history, allergies, and previous test results. The doctor may also perform a basic physical examination.
After the first consultation, there are usually two possibilities. If the condition is relatively clear, the doctor may directly provide a diagnosis, prescribe medication, or arrange outpatient treatment. If more information is needed, the doctor will order laboratory tests, imaging exams, or other examinations, such as blood tests, urine tests, X-ray, CT, ultrasound, ECG, or MRI.
If tests are ordered, the patient first pays for the tests, then goes to the relevant department to complete them. After the results are available, the patient returns to the doctor for a second consultation, also called result review. In this step, the doctor interprets the test results, confirms or adjusts the diagnosis, and decides the next treatment plan.
After the diagnosis and treatment plan are finalized, the patient pays the medical fees and then proceeds to the next step. This may include picking up medication, receiving outpatient treatment, making a follow-up appointment, being referred to another specialist, or being admitted to the hospital if the condition requires inpatient care.


### phase2(Synchronous modification of frontend and backend):
First，all process should be based on triage. conduct 5-level or triage: Reference: C:\Users\jangb\Desktop\hos\hos_formal\接口契约_v1.0.md, as for the less urgent and non- urgent use Outpatient process; the rest adopt the emergency process or  icu Rescue Procedure (placeholder only)
Secondly，For the clinical laboratory department, I may have already completed the relevant backend implementation, but the frontend may not be fully optimized yet. We will first develop an interactive version that does not connect to any agent. After the clinical laboratory process is completed, patients should be able to return to the corresponding outpatient department for further consultation.（Complete the transition of relevant statuses）

