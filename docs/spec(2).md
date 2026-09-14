# SPEC.md — JIT-Planned, Local-Execution GitHub Coding Agent

**Status:** Baseline implementation specification  
**Primary deployment target:** Hugging Face Docker Space, CPU-only  
**System of record:** GitHub  
**Primary coding model:** Spark-X2.5-1.7B Q4 via `llama.cpp`  
**Meta-planner:** JIT-Agent driven by a large-context cloud model  
**Idle PR reviewer:** Alibaba Open Code Review + MiniCPM5-2B Q4 via `llama.cpp`  
**Context optimization:** Headroom  
**Repository intelligence:** Graphify + Serena  
**Primary source-control tools:** `git` + GitHub CLI (`gh`)

---

## 1. Purpose

Build a self-hosted, GitHub-first coding agent that runs primarily on a Hugging Face CPU Space.

The system deliberately separates three forms of intelligence:

1. **Planning / harness generation** — a large-context cloud model, used through JIT-Agent, determines how a task should be executed.
2. **Coding execution** — a small local model, Spark-X2.5-1.7B Q4, performs bounded iterative coding work with a narrow set of task-specific tools.
3. **Independent PR review** — when the Space is otherwise idle, Alibaba Open Code Review uses MiniCPM5-2B Q4 to review open agent PRs. Detected issues may be handed back to the Spark execution worker for repair.

The architecture must be optimized for:
- CPU-only operation;
- low memory usage;
- small local-model context;
- deterministic Git/GitHub operations;
- task-specific tool exposure;
- recoverability;
- strict priority for interactive coding over maintenance work;
- disposable local storage, with GitHub as persistent state.

This is not intended to be a general multi-user cloud IDE. It is a lightweight autonomous GitHub coding worker.

---

# 2. Core architectural principles

## 2.1 GitHub is the source of truth

The Hugging Face filesystem is a temporary working cache.

Persistent project state must live in:
- Git repositories;
- branches;
- commits;
- pull requests;
- PR comments/reviews;
- GitHub issues where applicable.

The worker must always be able to reconstruct its working state from GitHub after a Space restart.

Do not make correctness depend on persistent local disks.

---

## 2.2 Cloud intelligence plans; local intelligence executes

The cloud model must not normally be the coding executor.

JIT-Agent should receive:
- task description;
- repository/task metadata;
- the approved capability registry;
- selected repository context;
- relevant prior harness patterns if available.

It returns a task-specific execution plan/harness.

Spark executes the task locally using that harness.

The objective is:

> Use the large cloud model to make the small local model's problem small.

---

## 2.3 Small-model tool surfaces must stay small

Do not expose every installed MCP/CLI tool to Spark for every task.

JIT's capability/tool-policy stage should choose a minimal allowlisted subset for each task.

Examples:

### Documentation edit
- file/symbol read;
- file edit;
- `git diff`;
- targeted validation.

### Bug fix
- Graphify query/impact;
- Serena symbol lookup/references/edit;
- targeted tests;
- `git diff`.

### Dependency migration
- Serena;
- Context7;
- `rg`;
- `ast-grep`;
- package manager;
- tests.

The execution model should never need to decide among dozens of irrelevant tools.

---

## 2.4 Deterministic operations stay outside the LLM where possible

The orchestrator should own:
- cloning;
- fetching;
- branch naming;
- checkout/reset;
- commits;
- pushes;
- PR creation;
- job locks;
- model process switching;
- idle scheduling;
- maximum repair cycles;
- timeouts;
- cancellation;
- workspace cleanup.

Do not ask Spark to perform administrative Git lifecycle operations unless a narrow exception is required.

---

## 2.5 Reviewer and author are separate roles

Spark authors/fixes code.

MiniCPM + Open Code Review critiques it.

MiniCPM should not silently mutate code during its review stage.

If review findings require fixes:
1. record structured findings;
2. stop/unload the review model;
3. switch back to Spark;
4. create a bounded repair task;
5. test;
6. push a new commit to the same PR branch;
7. queue the PR for re-review.

---

# 3. Runtime topology

Only one public service port is required.

```text
                           Internet
                              |
                              v
                  FastAPI / optional Gradio UI
                         :7860 public
                              |
                              v
                      Priority Scheduler
                              |
             +----------------+----------------+
             |                                 |
             v                                 v
        PRIMARY WORK                      IDLE WORK
        coding tasks                      maintenance
             |                                 |
             v                                 v
    JIT cloud meta-planner              Open PR queue
             |                                 |
             v                                 v
     generated task harness             Open Code Review
             |                                 |
             v                                 v
        Agent Executor                    MiniCPM5-2B
             |                                 |
             v                                 v
      Headroom :8787                    structured findings
             |                                 |
             v                                 |
    llama.cpp :8080 <--------------------------+
             |
      active model slot
             |
      Spark or MiniCPM
```

### Important

The initial implementation should use **one active local model slot**.

Do not keep Spark and MiniCPM loaded concurrently by default.

Model lifecycle:

```text
PRIMARY_CODING:
    Spark loaded
    MiniCPM unloaded

IDLE_REVIEW:
    Spark unloaded
    MiniCPM loaded

IDLE_FIX:
    MiniCPM unloaded
    Spark loaded
```

This keeps the deployment compatible with a small CPU-only machine.

---

# 4. Major components

## 4.1 API / UI layer

Preferred server:
- FastAPI on `0.0.0.0:7860`.

Optional:
- mount a small Gradio UI for manual task submission and observability;
- expose named Gradio API endpoints where useful.

The REST API is authoritative.

Initial endpoints:

```text
GET  /health
GET  /status

POST /tasks
GET  /tasks/{task_id}
GET  /tasks/{task_id}/events
POST /tasks/{task_id}/cancel

GET  /repos/{owner}/{repo}/status

GET  /maintenance/status
POST /maintenance/run
POST /maintenance/pause
```

Later:
- GitHub webhook endpoint;
- SSE/WebSocket task streaming;
- PR review endpoint;
- admin/model diagnostics.

---

## 4.2 Priority scheduler / resource arbiter

The Space has one scarce execution resource.

Use explicit job priorities.

```text
P0  user-requested primary coding
P1  requested repair/follow-up
P2  idle PR review
P3  idle automatic repair
P4  Graphify refresh / cleanup / housekeeping
```

Rules:

1. P0 always wins.
2. Maintenance work begins only after the configurable idle grace period.
3. A new P0 job must preempt maintenance.
4. Maintenance jobs must checkpoint enough state to restart later.
5. Never run two local inference-heavy jobs concurrently in v1.

Default configuration:

```text
IDLE_GRACE_SECONDS=180
MAX_AUTOMATIC_REPAIR_CYCLES=2
MAX_PRIMARY_JOB_SECONDS=1800
MAX_MAINTENANCE_JOB_SECONDS=1800
```

All values must be configurable.

---

# 5. Job state machine

Use explicit persisted/enumerated states.

```text
QUEUED
PREPARING_REPO
INDEXING
PLANNING
LOADING_EXEC_MODEL
EXECUTING
TESTING
VALIDATING
PUSHING
CREATING_PR
COMPLETED

IDLE_WAIT
LOADING_REVIEW_MODEL
REVIEWING
REVIEW_FINDINGS
QUEUED_FOR_REPAIR
REPAIRING
REREVIEW_PENDING

PREEMPTING
CANCELLED
FAILED
```

Task state must be observable through `/status` and task endpoints.

Do not infer job state from process existence alone.

---

# 6. Repository lifecycle

## 6.1 Workspace structure

Suggested layout:

```text
/workspace/
  repos/
    owner__repo/
      mirror-or-base-checkout/
  tasks/
    <task-id>/
      repo/
      artifacts/
      logs/
      harness/
  graphs/
    owner__repo/
      graph.json
  state/
    jobs.sqlite
```

Local state is disposable.

SQLite may be used for runtime state, but GitHub remains authoritative.

---

## 6.2 Opening a repository

For a new task:

1. validate `owner/repo` against repository policy;
2. authenticate using `GH_TOKEN`;
3. clone or fetch;
4. fetch target base branch;
5. reset a clean base checkout;
6. create a unique task branch or worktree;
7. inspect repository instructions:
   - `AGENTS.md`;
   - `README`;
   - language/package manifests;
   - project-specific agent files;
8. update Graphify index;
9. initialize Serena project context;
10. continue to planning.

Suggested branch format:

```text
agent/<task-slug>-<short-id>
```

Never modify `main`/default branch directly.

---

## 6.3 Git operations

Use `git` for:
- clone/fetch;
- branches/worktrees;
- status;
- diff;
- add;
- commit;
- push.

Use `gh` for:
- issue metadata;
- PR creation;
- PR metadata;
- checks;
- review comments if needed;
- GitHub API operations.

The orchestrator performs final Git mutations.

---

# 7. Primary coding flow

```text
POST /tasks
      |
      v
validate request
      |
      v
clone/fetch repo
      |
      v
create task branch/worktree
      |
      v
Graphify update/index
      |
      v
collect task context
      |
      v
JIT meta-planning using cloud model
      |
      v
validate generated harness/tool policy
      |
      v
load Spark-X2.5-1.7B Q4
      |
      v
bounded agent loop
      |
      +--> Graphify
      +--> Serena
      +--> selected MCP tools
      +--> selected CLI tools
      |
      v
targeted tests
      |
      v
static/security validation
      |
      v
Graphify impact check
      |
      v
git diff validation
      |
      v
commit + push
      |
      v
create/update PR
      |
      v
enqueue PR for idle review
```

---

# 8. JIT-Agent integration

Reference:
https://github.com/bingreeky/JIT

JIT-Agent is the meta-planning layer.

Its upstream architecture emits task-specific modules for:
- memory;
- planning;
- action;
- capability/tool policy;
- prompt.

Use a hosted OpenAI-compatible cloud model as the JIT meta-model.

Required environment:

```text
META_API_BASE=
META_API_KEY=
META_MODEL=
```

The local execution model is not the JIT cloud meta-model.

---

## 8.1 Do not blindly execute generated Python

Treat JIT-generated harness code as untrusted generated code.

V1 must introduce a safe adapter layer.

Preferred implementation approach:

1. define internal typed interfaces:
   - `MemoryPolicy`;
   - `PlanningPolicy`;
   - `ActionPolicy`;
   - `ToolPolicy`;
   - `ExecutionHarness`.

2. ask JIT/meta model for constrained structured output where possible;

3. if upstream JIT Python modules are reused:
   - parse/validate before execution;
   - reject forbidden imports;
   - reject filesystem/network/process access outside approved wrappers;
   - enforce step/token/time budgets;
   - execute in a restricted task workspace;
   - never allow generated code direct access to secrets.

4. capability calls must route through an approved registry.

The cloud model may choose tools from the registry. It may not invent executable capabilities.

---

## 8.2 Cloud context policy

Make repository disclosure configurable.

```text
META_CONTEXT_MODE=graph_only
META_CONTEXT_MODE=selected_files
META_CONTEXT_MODE=expanded
```

Default:
`selected_files`

JIT should normally receive:
- issue/task;
- repo map/Graphify summary;
- package/language metadata;
- relevant project instructions;
- selected symbols/files;
- allowed tool descriptions.

Avoid sending the entire private repository to a cloud model by default.

---

# 9. Local coding model

Primary model:

```text
Spark-X2.5-1.7B Q4
```

Reference:
https://github.com/XHToken/Spark-X2.5

Serve using `llama.cpp`.

Use an OpenAI-compatible local endpoint.

Suggested initial context budget:

```text
8K or 16K context
2K-4K maximum output
```

Do not configure the model's architectural maximum context merely because it exists.

Optimize for CPU prefill latency.

---

# 10. Headroom

Reference:
https://github.com/headroomlabs-ai/headroom

Headroom sits between the local agent executor and the local model endpoint.

Target topology:

```text
Agent Executor
      |
      v
Headroom :8787
      |
      v
llama.cpp :8080
```

Use a custom OpenAI-compatible upstream URL pointing to the local llama.cpp server.

Headroom's role:
- shrink long tool outputs;
- compress logs;
- reduce JSON/tool-result context;
- retain/retrieve originals where useful;
- expose metrics.

It is especially valuable for:
- test logs;
- compiler errors;
- Git diffs;
- MCP outputs;
- Graphify responses;
- large JSON.

Do not rely on Headroom as a substitute for good tool selection.

---

# 11. Repository intelligence

## 11.1 Graphify

Reference:
https://graphify.com/mcp

Graphify is the primary structural repository graph.

Responsibilities:
- repository indexing;
- callers/callees;
- dependency paths;
- blast-radius analysis;
- file ranking;
- structural queries.

Store local graph output per repository.

Typical tool capabilities:

```text
query_graph
graphify_node
graphify_callers
graphify_callees
graphify_trace
shortest_path
graphify_impact
graphify_rank_files
```

Run/update the graph:
- after clone/fetch;
- before a complex task if stale;
- after material code changes before final validation.

---

## 11.2 Serena

Reference:
https://github.com/oraios/serena

Serena supplies semantic code navigation/editing using LSP-backed symbolic understanding.

Preferred uses:
- symbol overview;
- find symbol;
- find references;
- find implementation;
- replace symbol body;
- insert before/after symbols;
- rename where supported.

For code exploration, prefer symbolic reads to full-file reads when possible.

Graphify answers:
> What is connected and where should we look?

Serena answers:
> Give me or edit this exact symbol.

---

# 12. MCP strategy

Provide an internal `ToolAdapter` abstraction so MCP tools and CLI tools look consistent to the execution loop.

Initial MCP servers:

### Required
- Graphify;
- Serena.

### Recommended
- restricted GitHub MCP, primarily read/context;
- Context7 for dependency/API documentation.

### Optional later
- Cognee for persistent project/agent memory.

Do not expose the full GitHub MCP tool surface to Spark.

Prefer deterministic `git`/`gh` orchestration for write actions.

---

# 13. CLI capability registry

Install and wrap at minimum:

```text
git
gh
rg
jq
ast-grep
patch
find
sed
curl
```

Testing tools are repository-specific.

Optional static analysis:
- Semgrep CLI.

CLI calls must be:
- timeout-bounded;
- cwd-restricted to the task workspace;
- logged;
- cancellable.

Avoid shell interpolation of untrusted user input.

---

# 14. Execution agent loop

Implement a lightweight bounded loop.

Conceptually:

```text
OBSERVE
  |
  v
THINK / PLAN NEXT STEP
  |
  v
SELECT ONE APPROVED ACTION
  |
  v
EXECUTE TOOL
  |
  v
COMPRESS / NORMALIZE RESULT
  |
  v
UPDATE WORKING MEMORY
  |
  +----> continue
  |
  v
DONE / FAIL / BUDGET EXHAUSTED
```

Required controls:
- max steps;
- max wall time;
- per-tool timeout;
- context budget;
- cancellation token;
- repeated-action detection;
- no-progress detection;
- maximum consecutive tool failures.

Suggested initial defaults:

```text
MAX_AGENT_STEPS=20
MAX_TOOL_FAILURES=3
MAX_IDENTICAL_ACTIONS=2
```

The JIT harness may tighten these values, but should not exceed server-configured hard maxima.

---

# 15. Validation before PR

Before commit/push:

1. inspect `git status`;
2. inspect diff summary;
3. reject unexpected generated/binary/secrets files;
4. run targeted tests;
5. run repository-required lint/typecheck if known;
6. optionally run Semgrep;
7. refresh Graphify;
8. perform impact query for changed important symbols;
9. ensure changes are scoped to the requested task;
10. ensure no direct modification of protected branches.

If tests fail:
- allow bounded correction loop;
- otherwise mark task failed and retain diff/logs for inspection.

---

# 16. PR creation

If the request mode is `pr`:

1. commit changes;
2. push task branch;
3. create PR with `gh pr create`;
4. include:
   - task summary;
   - tests run;
   - known limitations;
   - automated-agent marker;
   - task ID.

Suggested label:
`agent-generated`

Optional labels:
- `agent-review-pending`;
- `agent-review-clean`;
- `agent-review-needs-human`.

After PR creation:
- enqueue it for idle review;
- primary coding job is considered complete.

---

# 17. Idle-time review architecture

Reference:
https://github.com/alibaba/open-code-review

Review must only run while there is no primary coding work.

State:

```text
PRIMARY JOB FINISHES
       |
       v
IDLE_GRACE
       |
       v
select eligible open PR
       |
       v
unload Spark
       |
       v
load MiniCPM5
       |
       v
Open Code Review
       |
       v
structured findings
```

If a new primary task arrives at any point:
- mark review for preemption;
- stop at the next safe boundary or terminate;
- checkpoint findings/state;
- unload MiniCPM;
- load Spark;
- serve primary task.

---

# 18. MiniCPM review model

Reference:
https://github.com/OpenBMB/MiniCPM

Preferred initial review model:

```text
MiniCPM5-2B-Q4_K_M
```

Use `llama.cpp`.

Do not keep it loaded while Spark is serving primary coding jobs.

Open Code Review should call the local OpenAI-compatible endpoint.

Review responsibilities:
- correctness;
- regressions;
- security;
- concurrency/thread safety where relevant;
- SQL injection/XSS/etc. where relevant;
- performance problems;
- maintainability;
- precise line-level comments.

Use Open Code Review's deterministic pipeline/rules as the primary structure around the local review model.

---

# 19. Review-to-repair loop

Review findings should be stored in structured form.

If no meaningful findings:
- mark PR review clean;
- optionally comment summary;
- maintenance job ends.

If findings exist:

```text
MiniCPM review
     |
     v
structured findings
     |
     v
unload MiniCPM
     |
     v
load Spark
     |
     v
repair task on SAME PR branch
     |
     v
tests + validation
     |
     v
new commit + push
     |
     v
PR automatically updates
     |
     v
queue re-review
```

Do not create a new PR for ordinary review fixes.

Maximum automatic repair/re-review cycles per PR:

```text
2 by default
```

After the limit:
- stop automatic mutation;
- label/comment `needs-human-review`;
- preserve findings.

---

# 20. Prevent review/fix loops

Track:
- PR head SHA;
- review cycle number;
- finding fingerprints;
- applied repair commit;
- repeated findings.

Stop automation when:
- the same finding returns after repair;
- tests regress repeatedly;
- repair cycles exceed limit;
- the diff grows beyond configured scope;
- JIT/Spark reports low confidence;
- repository policy requires human approval.

---

# 21. Model manager

Implement a dedicated `ModelManager`.

Responsibilities:
- download/cache model artifacts;
- start `llama-server`;
- health-check it;
- stop it cleanly;
- switch between Spark and MiniCPM;
- enforce one active model;
- expose model state.

Interface example:

```text
ensure_model("spark")
ensure_model("minicpm-review")
stop_model()
health()
current_model()
```

Do not spread model lifecycle shell commands across handlers.

---

# 22. Process supervisor

The container needs lightweight supervision.

Long-lived components may include:
- FastAPI;
- Headroom;
- active llama.cpp server;
- optional MCP stdio subprocesses.

Prefer one Python process supervisor/orchestrator that starts and monitors children rather than a collection of fragile shell background processes.

Required:
- child health checks;
- stdout/stderr capture;
- graceful shutdown;
- restart policy for infrastructure processes;
- no automatic restart of a failed coding task.

---

# 23. Authentication and secrets

Expected secrets/config:

```text
GH_TOKEN=

META_API_BASE=
META_API_KEY=
META_MODEL=

HF_TOKEN=                 # only if model download requires it

ALLOWED_REPOS=
ALLOWED_GITHUB_ORGS=

IDLE_GRACE_SECONDS=180
MAX_AUTOMATIC_REPAIR_CYCLES=2
```

Potential Headroom-specific config:
```text
HEADROOM_PORT=8787
HEADROOM_MODE=token
```

Never:
- write secrets into repo files;
- include secrets in cloud JIT prompts;
- include secrets in PR bodies/comments;
- make secret values visible through `/status`;
- pass all process environment variables into tool subprocesses.

Use explicit per-process environment allowlists.

---

# 24. Repository security boundary

Repositories contain untrusted code.

V1 should support only explicitly allowed repositories/organizations.

Do not promise secure arbitrary-public-repository execution on the same host that contains GitHub/cloud API secrets.

For v1:
- repository allowlist;
- command timeouts;
- no privileged container operations;
- run task processes as non-root where practical;
- restrict cwd;
- restrict environment;
- sanitize logs.

Future:
- isolate execution through SWE-ReX or another sandbox/worker boundary.

---

# 25. API request schema

Suggested initial request:

```json
{
  "repo": "owner/repository",
  "base": "main",
  "task": "Fix issue #52 where refresh tokens leave stale cache entries.",
  "mode": "pr",
  "issue": 52,
  "meta_context_mode": "selected_files"
}
```

Modes:
- `workspace` — modify/test but do not push;
- `push` — push branch but no PR;
- `pr` — push and create PR.

Default:
`pr`

Response:

```json
{
  "task_id": "task_...",
  "status": "queued"
}
```

Task result should later contain:

```json
{
  "task_id": "task_...",
  "status": "completed",
  "repo": "owner/repository",
  "branch": "agent/fix-refresh-cache-ab12",
  "commit": "...",
  "pr_url": "...",
  "tests": [],
  "changed_files": [],
  "review_status": "queued"
}
```

---

# 26. Observability

Expose structured events.

At minimum record:
- task ID;
- repo;
- branch;
- state transitions;
- selected JIT harness/tool policy;
- model currently loaded;
- agent step number;
- tools called;
- test status;
- context size;
- Headroom token/compression stats if available;
- PR URL;
- review cycle;
- failure reason.

Never expose chain-of-thought.

Store:
- concise model-visible working summaries;
- structured actions/results;
- system metrics.

---

# 27. Recovery after Space restart

At startup:

1. check infrastructure;
2. validate GitHub auth;
3. inspect runtime DB if present;
4. mark interrupted local-only jobs as interrupted;
5. reconcile known pushed branches/PRs against GitHub;
6. reconstruct idle review queue from GitHub;
7. do not automatically recreate unpushed code that existed only on ephemeral disk;
8. expose recovery status.

Because GitHub is authoritative, review jobs should be reconstructable from open PR state.

---

# 28. Suggested code structure

```text
app/
  main.py

  api/
    routes_health.py
    routes_tasks.py
    routes_maintenance.py

  config/
    settings.py

  scheduler/
    priority_queue.py
    arbiter.py
    states.py

  repos/
    manager.py
    github.py
    git.py
    workspace.py

  planning/
    jit_client.py
    harness_schema.py
    harness_validator.py
    context_builder.py

  agent/
    loop.py
    executor.py
    memory.py
    budgets.py

  tools/
    registry.py
    base.py
    cli.py
    mcp.py
    graphify.py
    serena.py
    context7.py

  models/
    manager.py
    llama_server.py
    headroom.py

  validation/
    tests.py
    diff.py
    semgrep.py
    impact.py

  review/
    queue.py
    open_code_review.py
    findings.py
    repair.py

  state/
    db.py
    models.py

scripts/
  bootstrap.sh
  healthcheck.sh

tests/
  unit/
  integration/
  fixtures/

SPEC.md
README.md
Dockerfile
```

This is guidance, not a rigid requirement. Keep boundaries clear even if exact paths differ.

---

# 29. Docker / HF Space requirements

Target a Hugging Face Docker Space.

Public:
```text
7860
```

Internal only:
```text
8787 Headroom
8080 llama.cpp active model
```

Install:
- Python;
- Node.js if required by Open Code Review/OpenCode dependencies;
- Git;
- GitHub CLI;
- `ripgrep`;
- `jq`;
- `ast-grep`;
- `curl`;
- build prerequisites;
- `llama.cpp`;
- JIT-Agent dependencies;
- Graphify;
- Serena;
- Headroom;
- Alibaba Open Code Review.

Model files should be downloaded during runtime/bootstrap when practical rather than permanently baking large weights into the image.

Use HF cache directories consistently.

---

# 30. Development phases

## Phase 0 — Repository audit

Before changing architecture:
- inspect existing project;
- identify current API behavior;
- preserve useful existing endpoints;
- identify Docker/HF constraints;
- create an implementation plan mapped to this spec.

Do not immediately rewrite the whole repository.

---

## Phase 1 — GitHub-first execution skeleton

Implement:
- config;
- FastAPI health/status;
- job model;
- priority scheduler;
- repo manager;
- `GH_TOKEN` auth;
- clone/fetch;
- branch/worktree creation;
- deterministic commit/push/PR flow;
- mock executor.

Acceptance:
- submit a task against an allowed test repo;
- service creates a task branch;
- mock file change can be committed;
- branch can be pushed;
- PR can be created;
- no LLM required yet.

---

## Phase 2 — Local model runtime

Implement:
- `llama.cpp` model manager;
- Spark model download/start/stop;
- OpenAI-compatible health checks;
- Headroom proxy to local llama.cpp;
- basic bounded agent-loop abstraction.

Acceptance:
- Spark returns a model response through Headroom;
- only one model process is active;
- process survives multiple sequential requests;
- context metrics are observable.

---

## Phase 3 — Repository intelligence

Implement:
- Graphify index/update;
- Graphify tool adapter;
- Serena MCP adapter;
- capability registry;
- `rg`, `ast-grep`, tests wrappers.

Acceptance:
- a task can query Graphify;
- retrieve/edit a symbol via Serena;
- run a targeted test;
- record tool events.

---

## Phase 4 — JIT cloud meta-planning

Implement:
- JIT cloud model client/integration;
- task context builder;
- capability descriptions;
- constrained harness representation;
- harness validation;
- dynamic tool subset selection.

Acceptance:
- cloud planner creates a valid task harness;
- invalid/unsafe harness is rejected or repaired;
- Spark receives only the selected capabilities;
- hard server budgets cannot be overridden by generated harnesses.

---

## Phase 5 — End-to-end coding PR

Implement full flow:
- task;
- plan;
- edit;
- test;
- validate;
- commit;
- push;
- PR.

Acceptance:
- small real repo issue can be solved end-to-end;
- restart does not corrupt GitHub state;
- task result contains PR URL and validation summary.

---

## Phase 6 — Idle review

Implement:
- idle grace timer;
- review queue discovery;
- model switching Spark -> MiniCPM;
- Alibaba Open Code Review;
- structured finding capture;
- preemption on new primary job.

Acceptance:
- review starts only while primary queue is empty;
- new primary task interrupts review;
- MiniCPM is unloaded before Spark starts;
- line-level findings can be attached/stored for a PR.

---

## Phase 7 — Autonomous repair

Implement:
- review finding -> repair task;
- checkout same PR branch;
- JIT repair harness;
- Spark repair;
- tests;
- push;
- re-review queue;
- repair-cycle limits.

Acceptance:
- issue discovered during idle review can result in a new commit on the same PR;
- no infinite review/fix loop;
- unresolved repeated finding triggers human-review state.

---

# 31. Test strategy

## Unit tests
- scheduler priority/preemption;
- job state transitions;
- branch naming;
- repo allowlist;
- harness validator;
- tool policy validation;
- command timeout;
- repeated-action detection;
- review-cycle limit;
- environment secret filtering.

## Integration tests
Use a small fixture Git repository.

Test:
1. clone;
2. branch;
3. Graphify index;
4. Serena query;
5. mock/JIT harness;
6. agent tool call;
7. diff;
8. test;
9. commit;
10. push stub/test remote;
11. PR creation adapter.

## Model integration tests
Keep optional and marked slow:
- Spark via Headroom;
- MiniCPM;
- model switching;
- idle preemption.

Do not make every CI run download multiple GGUF models.

---

# 32. Acceptance criteria for v1

The system is v1-ready when:

- [ ] Runs as one HF Docker Space on CPU.
- [ ] Exposes health/status/task APIs on port 7860.
- [ ] GitHub is the persistent source of repository state.
- [ ] Primary coding tasks always preempt maintenance.
- [ ] Cloud JIT meta-model produces validated task-specific harness/tool policy.
- [ ] Spark-X2.5-1.7B Q4 performs local execution.
- [ ] Headroom sits on the Spark request path.
- [ ] Graphify is used for structural repository intelligence.
- [ ] Serena is used for semantic/symbolic code operations.
- [ ] Agent tool surface is task-specific and allowlisted.
- [ ] Git/PR lifecycle is deterministic and orchestrator-owned.
- [ ] PRs are reviewed only during idle time.
- [ ] Open Code Review uses local MiniCPM5-2B Q4.
- [ ] MiniCPM and Spark are not normally resident concurrently.
- [ ] Review findings can trigger bounded automatic repair on the same PR.
- [ ] Maximum repair/re-review cycles are enforced.
- [ ] Incoming primary task can preempt review/repair.
- [ ] Repo execution is allowlisted and secrets are isolated.
- [ ] Service can recover useful state from GitHub after restart.

---

# 33. Explicit non-goals for v1

Do not build these before the core loop works:

- arbitrary untrusted public-repo sandboxing;
- multi-tenant isolation;
- simultaneous multi-model inference;
- multiple simultaneous coding workers;
- full IDE/browser environment;
- persistent vector database;
- Neo4j/FalkorDB infrastructure;
- heavy autonomous browser tooling;
- continuous background review while the HF Space itself is asleep;
- automatic merge to protected branches;
- unrestricted self-modification of the worker.

---

# 34. Reference projects

JIT-Agent  
https://github.com/bingreeky/JIT

Spark-X2.5  
https://github.com/XHToken/Spark-X2.5

Headroom  
https://github.com/headroomlabs-ai/headroom

Graphify MCP  
https://graphify.com/mcp

Serena  
https://github.com/oraios/serena

Alibaba Open Code Review  
https://github.com/alibaba/open-code-review

MiniCPM / MiniCPM5  
https://github.com/OpenBMB/MiniCPM

GitHub CLI  
https://cli.github.com/

Optional later:
- Cognee for persistent project memory;
- SWE-ReX or equivalent for stronger execution isolation.

---

# 35. Guidance to implementation agents

When implementing this spec:

1. inspect the current repository before changing it;
2. reuse existing working code where possible;
3. implement incrementally;
4. do not replace working API behavior without a reason;
5. keep infrastructure adapters behind interfaces;
6. keep external projects loosely coupled;
7. pin dependency versions once proven;
8. add tests with each phase;
9. favor deterministic code over LLM decisions;
10. do not weaken security boundaries for convenience;
11. do not add heavyweight infrastructure unless an acceptance criterion requires it;
12. update this spec when implementation reality requires an architectural change.

If a reference project's current API differs from assumptions in this document, prefer the project's current supported API and document the deviation.

---

# 36. First implementation milestone

The first milestone is intentionally **not** “make the AI solve a repository issue.”

It is:

> Build a reliable GitHub-first task runner with job priority/state, repository checkout/branch isolation, deterministic push/PR behavior, process supervision, and clean extension points for JIT, local models, MCP tools, and idle review.

Once that substrate is reliable, add local inference and intelligence layers incrementally.

This ordering is mandatory unless the existing repository already provides those foundations.
