# MetroPT-3 Recruiter Packaging Design

- Date: 2026-10-29
- Status: Approved
- Scope: Public demo, repository packaging, deployment documentation, and recruiter-facing narrative

## 1. Objective

Make the completed MetroPT-3 maintenance analytics project easy for recruiters and interviewers to verify within a few minutes.

The packaging must expose:

1. A public, no-login application.
2. A clear industrial data and maintenance analytics business narrative.
3. Traceable evidence for SQL metrics, data quality, event provenance, and weekly report export.
4. Explicit data and interpretation limits.
5. A concise resume and interview presentation.

The packaging must not change the core business logic, metric definitions, SQL semantics, or current local full-data workflow.

## 2. Audience

Primary audience:

- Recruiters and hiring managers for manufacturing digitalization, industrial data, equipment maintenance analytics, and industrial solution roles.

Secondary audience:

- Interviewers who need to inspect technical decisions, SQL, data quality handling, testing, and limitations.

## 3. Success Criteria

The packaging is complete when:

- The public repository is accessible without credentials.
- The public Streamlit demo opens without login.
- The demo defaults to the complete week of 2020-06-01 through 2020-06-08.
- The demo visibly states that it uses a representative subset rather than the full dataset.
- Event detail, source traceability, and weekly report export work in the public demo.
- Database credentials are supplied through Streamlit Secrets and are not committed.
- Raw source data is excluded from Git and remains documented with its source and checksum.
- README communicates the business problem, key result, live demo, limitations, and evidence path above the technical architecture.
- The repository contains a one-page Chinese case study, deployment instructions, a 90-second demo script, and resume bullets.
- Existing tests continue to pass, or packaging-specific tests are added without weakening current validation.

## 4. Non-Goals

- Add AI inference, prediction, anomaly detection, or chat features.
- Add hardware engineering claims.
- Change SQL metric definitions.
- Calculate OEE, MTTR, availability, cost savings, or MTBF.
- Deploy the complete 639 MB database to a free tier.
- Upload the 208 MB CSV or 27.75 MB ZIP to Git.
- Turn the repository into a multi-device platform.
- Teach or introduce new SQL concepts as part of packaging.

## 5. Public Architecture

Public path:

`GitHub public repository -> Streamlit Community Cloud -> Neon free PostgreSQL`

Responsibilities:

- GitHub stores code, demo seed data, screenshots, audit evidence, deployment documentation, and tests.
- Neon stores only the representative demo week.
- Streamlit Community Cloud runs the application from the public repository.
- Streamlit Secrets stores the PostgreSQL connection URL.

The existing local Docker Compose workflow remains the full-data development and verification path.

## 6. Demo Data Strategy

Public demo period:

- Start: 2020-06-01 00:00:00 UTC
- End: 2020-06-08 00:00:00 UTC

Demo content:

- Include the complete telemetry for this week.
- Include failure event E03, which lasts 52.5 hours.
- Preserve the original source identifiers and row references needed for traceability.
- Preserve the relevant gap records and weekly reporting behavior.
- Do not splice together non-contiguous event windows.

The public application must display a persistent notice such as:

> Online demo uses a representative one-week subset. Full-data evidence is documented in the repository.

README must separately retain full-data results for all four failure events and the complete data audit.

## 7. Recruiter Journey

The first README viewport should contain, in order:

1. Project title and one-sentence industrial data positioning.
2. Links to the live demo and 90-second demonstration.
3. Three headline evidence points from the full dataset.
4. A desktop screenshot.
5. A concise "what I built" list.
6. Explicit limitations.

The detailed architecture, SQL, tests, audit reports, and local reproduction steps follow after the first viewport.

The public app should support a short demonstration path:

1. Open the demo week.
2. Inspect E03 and its 52.5-hour duration.
3. Trace the event to source identifiers and telemetry samples.
4. Review the data-quality notice.
5. Export the weekly report.

## 8. Deliverables

Repository files to add or update:

- `README.md`: recruiter-first entry point.
- `docs/case_study.md`: one-page Chinese business and technical case.
- `docs/deployment.md`: Neon, Streamlit Secrets, demo import, and publication steps.
- `docs/demo_script.md`: six-action, 90-second demonstration script.
- `docs/resume_bullets.md`: one project title and three evidence-based bullets.
- `data/demo/`: deterministic representative-week data.
- `scripts/load_demo_db.py`: load and validate only the demo week without changing full-data validation.
- `.streamlit/secrets.toml.example`: connection template without credentials.
- `.gitignore`: exclude raw data, database volumes, caches, generated local files, and secrets.
- `.dockerignore`: reduce image context and exclude large local data when not required.
- `LICENSE`: code license.
- Data attribution section or file: distinguish source data licensing from code licensing.

The packaging may add a small demo-mode notice or deployment configuration to application entry points, but it must not alter metric queries or business semantics.

## 9. Security and Data Handling

- Never commit the Neon connection string.
- Do not commit `.streamlit/secrets.toml`.
- Do not commit `data/raw/`.
- Do not commit database dumps containing credentials or private environment data.
- Publish only the public MetroPT-3 source and derived representative-week data.
- Preserve source attribution and document the source checksum already produced by the audit.

## 10. Narrative Rules

Resume project title:

> Industrial Equipment Maintenance Data Analytics Platform | Python / PostgreSQL / SQL / Streamlit

Chinese resume title:

> 工业设备维护数据分析平台｜Python / PostgreSQL / SQL / Streamlit

The narrative must not claim:

- AI diagnosis or failure prediction.
- Hardware research or embedded engineering.
- Real production savings.
- Full-fleet generalization.
- OEE, MTTR, availability, or MTBF.

The defensible value proposition is:

- Audited a large, imperfect industrial telemetry dataset.
- Built reproducible SQL metrics and source traceability.
- Produced a decision-support weekly report.
- Explicitly documented assumptions and limitations.

## 11. Verification

Packaging verification must include:

- Run the existing test suite.
- Validate the demo loader row counts and event scope.
- Start the application against the demo database.
- Verify the demo week, event trace, and report download in a browser.
- Check that no secrets or raw files are staged for Git.
- Verify README links, screenshots, and deployment commands.
- Verify the public application after deployment.

## 12. Acceptance

The design is accepted when the repository and public demo let an interviewer answer:

1. What business question does this solve?
2. What did the candidate personally build?
3. Can the result be reproduced and traced?
4. Are the data limitations represented honestly?
5. Can the application be operated without the candidate explaining every click?

