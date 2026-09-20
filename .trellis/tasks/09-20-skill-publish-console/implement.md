# Skill 发布管理台 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 NAS 上部署独立 Skill 管理台，安全管理本地与 GitHub Skill，并以 Linux symlink 发布到宿主机 OpenClaw/Hermes。

**Architecture:** `apps/skill-manager` 提供 `/skills` 双栏工作台；`backend/skill-manager` 负责注册表、GitHub 缓存、密码验证、SQLite 审计和受限目录内的原子 symlink 发布。Nginx 将 `/skills` 与 `/api/skills` 分别反代到两个服务，Compose 只将五个明确的 NAS 目录挂入后端。

**Tech Stack:** Next.js 15 + React 19 + TypeScript + Tailwind；FastAPI + Pydantic Settings + SQLite + pytest；Git CLI；Docker Compose、Nginx、Linux symbolic link。

---

## File structure

| 路径 | 职责 |
|---|---|
| `F:/personal-projects/skills/registry.json` | 可版本控制的 Skill 登记真源，替代 HTML 内嵌 JSON。 |
| `backend/skill-manager/src/config.py` | 受限 NAS 路径、密码、端口与 Git 设置。 |
| `backend/skill-manager/src/models.py` | 注册表、发布计划、API 请求/响应的唯一 Pydantic 契约。 |
| `backend/skill-manager/src/db.py` | SQLite schema 与发布/快照读写。 |
| `backend/skill-manager/src/services/registry.py` | `registry.json` 校验、原子写入与本地 Skill 扫描。 |
| `backend/skill-manager/src/services/git_cache.py` | GitHub URL 校验、临时扫描、版本检查、缓存 checkout。 |
| `backend/skill-manager/src/services/publisher.py` | 目标路径白名单、临时 symlink、原子发布、下架与回滚。 |
| `backend/skill-manager/src/api/routes.py` | HTTP 边界、密码守卫、批量发布结果。 |
| `apps/skill-manager/src/app/page.tsx` | 左侧筛选池、右侧队列、计划预览和确认交互。 |
| `apps/skill-manager/src/lib/api.ts` / `types.ts` | 唯一前端 API 客户端与共享 UI 数据模型。 |
| `docker-compose.nas.yml`、`nginx/web.conf`、`scripts/deploy-nas.sh` | NAS 服务、受限挂载、路径路由与部署入口。 |

## Task 1: Bootstrap the backend with explicit configuration and contracts

**Files:**

- Create: `backend/skill-manager/pyproject.toml`
- Create: `backend/skill-manager/Dockerfile`
- Create: `backend/skill-manager/src/__init__.py`
- Create: `backend/skill-manager/src/config.py`
- Create: `backend/skill-manager/src/models.py`
- Create: `backend/skill-manager/src/main.py`
- Create: `backend/skill-manager/tests/test_config.py`
- Create: `backend/skill-manager/tests/test_models.py`

- [ ] **Step 1: Write failing configuration tests.**

```python
def test_settings_rejects_target_outside_its_mount(monkeypatch, tmp_path):
    monkeypatch.setenv("SKILLS_SOURCE_ROOT", str(tmp_path / "source"))
    monkeypatch.setenv("GITHUB_SKILL_CACHE_ROOT", str(tmp_path / "cache"))
    monkeypatch.setenv("SKILL_MANAGER_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("OPENCLAW_SKILLS_ROOT", str(tmp_path / "outside"))
    monkeypatch.setenv("HERMES_SKILLS_ROOT", str(tmp_path / "targets" / "hermes"))
    monkeypatch.setenv("SKILL_MANAGER_ADMIN_PASSWORD", "test-password")

    with pytest.raises(ValueError, match="target root"):
        Settings(targets_mount_root=tmp_path / "targets")
```

- [ ] **Step 2: Run the new tests and verify failure.**

Run: `cd backend/skill-manager && uv run pytest tests/test_config.py tests/test_models.py -v`

Expected: FAIL because the package and `Settings` do not exist.

- [ ] **Step 3: Implement the backend skeleton and contracts.**

Define `Settings` with `Path` fields for the five mounted roots, `admin_password: SecretStr`, `service_port: int = 8097`, and `targets_mount_root`. Its post-validation must resolve every configured root, require it to exist, and require both target roots to be descendants of `targets_mount_root`. Define these Pydantic models once in `models.py` and import them everywhere else:

```python
class SkillSource(StrEnum):
    LOCAL = "local"
    GITHUB = "github"

class TargetKey(StrEnum):
    OPENCLAW = "openclaw"
    HERMES = "hermes"

class RegistrySkill(BaseModel):
    id: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9-]{0,62}$")]
    name: str
    source: SkillSource
    path: str
    repository: HttpUrl | None = None
    tags: list[Annotated[str, Field(min_length=1, max_length=40)]] = []
    summary: str = ""
    status: Literal["active", "deprecated"] = "active"
```

Create `FastAPI(title="skill-manager")`, include an `/api/health` endpoint returning `{"status": "ok"}`, and configure the Docker image to run `uvicorn src.main:app --host 0.0.0.0 --port 8097`.

- [ ] **Step 4: Run backend tests and health import check.**

Run: `cd backend/skill-manager && uv sync --all-groups && uv run pytest tests/test_config.py tests/test_models.py -v && uv run python -c "from src.main import app; assert app.title == 'skill-manager'"`

Expected: PASS.

- [ ] **Step 5: Commit the bootstrap.**

Run: `git add backend/skill-manager && git commit -m "feat(skill-manager): 初始化后端服务契约"`

## Task 2: Move the registry to JSON and implement validated local discovery

**Files:**

- Create: `backend/skill-manager/src/services/__init__.py`
- Create: `backend/skill-manager/src/services/registry.py`
- Create: `backend/skill-manager/scripts/migrate_registry.py`
- Create: `backend/skill-manager/tests/test_registry.py`
- Create: `F:/personal-projects/skills/registry.json`
- Modify: `F:/personal-projects/skills/README.md`
- Modify: `F:/personal-projects/skills/scripts/sync_skills.py`
- Modify: `F:/personal-projects/skills/scripts/sync_github_skills.py`
- Modify: `F:/personal-projects/skills/scripts/sync_github_versions.py`

- [ ] **Step 1: Write failing registry tests.**

```python
def test_registry_rejects_local_path_escape(registry_service, tmp_path):
    escaped = RegistrySkill(id="escape", name="Escape", source="local", path="../outside")
    with pytest.raises(RegistryValidationError, match="source root"):
        registry_service.upsert(escaped)

def test_registry_lists_only_local_directories_with_skill_md(registry_service, source_root):
    (source_root / "ok").mkdir()
    (source_root / "ok" / "SKILL.md").write_text("---\nname: ok\n---", encoding="utf-8")
    (source_root / "not-a-skill").mkdir()

    assert [skill.id for skill in registry_service.discover_local()] == ["ok"]
```

- [ ] **Step 2: Run the registry tests and verify failure.**

Run: `cd backend/skill-manager && uv run pytest tests/test_registry.py -v`

Expected: FAIL because `RegistryService` and migration output do not exist.

- [ ] **Step 3: Implement JSON migration and registry ownership.**

Write `migrate_registry.py` to read the current `registry-data` script block once, convert current `dir`/`repo`/`theme` entries to the `RegistrySkill` schema (`theme` becomes a single tag), preserve IDs deterministically, and write `${SKILLS_SOURCE_ROOT}/registry.json` with atomic `os.replace`. Do not silently delete the old HTML registry; update its page to load/download the JSON or mark it deprecated in README after migration succeeds.

`RegistryService` must load only `registry.json`, normalize every relative path with `Path.resolve()`, verify descendants with `path.is_relative_to(root)`, require `SKILL.md`, reject duplicate IDs/repositories/path pairs, sort and deduplicate tags, and atomically rewrite valid registry JSON. Its optional `commit_registry_change()` can run only a fixed `git add registry.json && git commit` argument list; no browser values enter a command string.

- [ ] **Step 4: Update the legacy sync scripts to consume `registry.json`.**

Replace each script's HTML regex parser with one shared `load_registry()` that reads `ROOT / "registry.json"`; preserve its existing `--status`, `--skill`, `--agent`, `--dry-run` behavior. Keep `sync-config.json` as machine-local target configuration, but make agent assignment an explicit `agents` object in `registry.json`.

- [ ] **Step 5: Run migration and regression tests.**

Run: `cd backend/skill-manager && uv run pytest tests/test_registry.py -v && uv run python scripts/migrate_registry.py --source-root F:/personal-projects/skills --dry-run`

Expected: PASS; dry run prints the number of migrated skills and makes no write.

- [ ] **Step 6: Commit registry migration support.**

Run: `git add backend/skill-manager F:/personal-projects/skills && git commit -m "feat(skills): 迁移技能注册表到 JSON"`

## Task 3: Build the SQLite audit store and safe Linux publisher

**Files:**

- Create: `backend/skill-manager/src/db.py`
- Create: `backend/skill-manager/src/services/publisher.py`
- Create: `backend/skill-manager/tests/test_publisher.py`
- Create: `backend/skill-manager/tests/test_db.py`

- [ ] **Step 1: Write failing filesystem and rollback tests.**

```python
def test_publish_replaces_only_a_managed_symlink(publisher, source_dir, openclaw_root):
    published = publisher.publish("research-skill", TargetKey.OPENCLAW, source_dir, "sha-1")
    assert (openclaw_root / "research-skill").is_symlink()
    assert (openclaw_root / "research-skill").resolve() == source_dir
    assert published.action == "add"

def test_publish_refuses_to_overwrite_a_real_directory(publisher, source_dir, openclaw_root):
    (openclaw_root / "research-skill").mkdir()
    with pytest.raises(PublishBlockedError, match="ordinary directory"):
        publisher.publish("research-skill", TargetKey.OPENCLAW, source_dir, "sha-1")

def test_rollback_restores_the_previous_link(publisher, source_v1, source_v2, openclaw_root):
    publisher.publish("research-skill", TargetKey.OPENCLAW, source_v1, "sha-1")
    publisher.publish("research-skill", TargetKey.OPENCLAW, source_v2, "sha-2")
    publisher.rollback("research-skill", TargetKey.OPENCLAW)
    assert (openclaw_root / "research-skill").resolve() == source_v1
```

- [ ] **Step 2: Run tests and verify failure.**

Run: `cd backend/skill-manager && uv run pytest tests/test_publisher.py tests/test_db.py -v`

Expected: FAIL because the publisher and persistence schema do not exist.

- [ ] **Step 3: Implement persistence and atomic links.**

Create SQLite tables `deployment`, `deployment_history`, and `rollback_snapshot`, keyed by `(skill_id, target)`. Implement `Publisher.publish()` to: validate skill ID; validate source `SKILL.md` and allowed source root; create `<target>/.{skill_id}.{uuid}.next`; validate the link resolves to source; snapshot an existing managed link; use `os.replace(temp_link, final_link)`; then persist status/revision/history. Implement `unpublish()` with `Path.unlink()` only after verifying a managed symlink, never `rmtree`. Implement `rollback()` by replaying the stored snapshot through the same temporary-link flow.

- [ ] **Step 4: Add one-item failure isolation test and run all publisher tests.**

```python
def test_batch_keeps_successful_item_when_another_target_is_blocked(publisher, source_dir, roots):
    (roots.hermes / "blocked-skill").mkdir()
    result = publisher.publish_many([
        PublishItem(skill_id="good-skill", target=TargetKey.OPENCLAW, source=source_dir),
        PublishItem(skill_id="blocked-skill", target=TargetKey.HERMES, source=source_dir),
    ])
    assert [item.status for item in result.items] == ["success", "blocked"]
    assert (roots.openclaw / "good-skill").is_symlink()
```

Run: `cd backend/skill-manager && uv run pytest tests/test_publisher.py tests/test_db.py -v`

Expected: PASS.

- [ ] **Step 5: Commit safe publishing.**

Run: `git add backend/skill-manager && git commit -m "feat(skill-manager): 实现安全技能发布与回滚"`

## Task 4: Add GitHub discovery, update checks, and cache checkout

**Files:**

- Create: `backend/skill-manager/src/services/git_cache.py`
- Create: `backend/skill-manager/tests/test_git_cache.py`
- Modify: `backend/skill-manager/src/models.py`
- Modify: `backend/skill-manager/src/services/registry.py`

- [ ] **Step 1: Write failing GitHub service tests using a local bare Git fixture.**

```python
def test_scan_returns_each_skill_md_directory(git_cache, github_repo_with_two_skills):
    candidates = git_cache.scan("https://github.com/example/two-skills")
    assert [candidate.path for candidate in candidates] == ["skills/alpha", "skills/beta"]

def test_scan_rejects_non_github_and_file_urls(git_cache):
    for url in ("file:///tmp/skill", "ssh://git@github.com/a/b", "https://gitlab.com/a/b"):
        with pytest.raises(InvalidRepositoryError):
            git_cache.scan(url)

def test_check_updates_does_not_change_cache(git_cache, registered_github_skill):
    before = git_cache.current_revision(registered_github_skill.id)
    update = git_cache.check_update(registered_github_skill)
    assert git_cache.current_revision(registered_github_skill.id) == before
    assert update.remote_revision
```

- [ ] **Step 2: Run tests and verify failure.**

Run: `cd backend/skill-manager && uv run pytest tests/test_git_cache.py -v`

Expected: FAIL because repository validation and cache service do not exist.

- [ ] **Step 3: Implement controlled Git operations.**

Use `subprocess.run([...], shell=False, check=True, timeout=60)` with fixed Git arguments. Normalize only `https://github.com/<owner>/<repo>[.git]`, clone scans under `${STATE_DIR}/scan/<uuid>`, ignore `.git` and hidden directories during `SKILL.md` discovery, and always remove scan workspaces in `finally`. `check_update()` uses `git ls-remote --tags --refs` plus `HEAD`, writes only `github_check`, and never fetches cache. `ensure_cached()` fetches the repository to `${GITHUB_SKILL_CACHE_ROOT}/${skill.id}`, checks out a concrete tag/commit, and verifies the registered `path/SKILL.md` before returning it.

- [ ] **Step 4: Add update/cache regression cases and run tests.**

```python
def test_cache_checkout_rejects_missing_registered_subdirectory(git_cache, registered_github_skill):
    registered_github_skill.path = "gone"
    with pytest.raises(CacheValidationError, match="SKILL.md"):
        git_cache.ensure_cached(registered_github_skill, "abc1234")
```

Run: `cd backend/skill-manager && uv run pytest tests/test_git_cache.py tests/test_registry.py -v`

Expected: PASS.

- [ ] **Step 5: Commit GitHub lifecycle support.**

Run: `git add backend/skill-manager && git commit -m "feat(skill-manager): 支持 GitHub 技能扫描与更新"`

## Task 5: Expose the protected FastAPI API and plan endpoint

**Files:**

- Create: `backend/skill-manager/src/api/__init__.py`
- Create: `backend/skill-manager/src/api/dependencies.py`
- Create: `backend/skill-manager/src/api/routes.py`
- Create: `backend/skill-manager/tests/test_api.py`
- Modify: `backend/skill-manager/src/main.py`

- [ ] **Step 1: Write failing API tests.**

```python
def test_list_skills_is_public(client):
    response = client.get("/api/skills")
    assert response.status_code == 200
    assert response.json()["items"]

def test_publish_requires_correct_password(client, publish_request):
    assert client.post("/api/skills/publish", json={**publish_request, "password": "wrong"}).status_code == 401
    assert client.post("/api/skills/publish", json={**publish_request, "password": "correct"}).status_code == 200

def test_plan_does_not_mutate_links(client, plan_request, openclaw_root):
    response = client.post("/api/skills/publish/plan", json=plan_request)
    assert response.status_code == 200
    assert not any(openclaw_root.iterdir())
```

- [ ] **Step 2: Run tests and verify failure.**

Run: `cd backend/skill-manager && uv run pytest tests/test_api.py -v`

Expected: FAIL because `/api/skills` routes are absent.

- [ ] **Step 3: Implement routes and a single password guard.**

Use `hmac.compare_digest(submitted, settings.admin_password.get_secret_value())` in one dependency. Keep password-bearing request models separate from public plan models. Add public list, scan, update-check, and plan routes; add protected register, publish, rollback, and delete routes. The publish endpoint must return a batch result with one result per requested `skill_id × target`; expected per-item filesystem errors return a `status`/`code`/`message` result rather than rolling back unrelated successful items. Route errors use `{ "code": "...", "message": "..." }` consistently.

- [ ] **Step 4: Run API tests and an ASGI health test.**

Run: `cd backend/skill-manager && uv run pytest tests/test_api.py tests/test_publisher.py tests/test_git_cache.py -v`

Expected: PASS.

- [ ] **Step 5: Commit the API layer.**

Run: `git add backend/skill-manager && git commit -m "feat(skill-manager): 提供发布管理 API"`

## Task 6: Build the Next.js dual-pane management workspace

**Files:**

- Create: `apps/skill-manager/package.json`
- Create: `apps/skill-manager/tsconfig.json`
- Create: `apps/skill-manager/next.config.js`
- Create: `apps/skill-manager/Dockerfile`
- Create: `apps/skill-manager/src/app/layout.tsx`
- Create: `apps/skill-manager/src/app/page.tsx`
- Create: `apps/skill-manager/src/app/globals.css`
- Create: `apps/skill-manager/src/lib/types.ts`
- Create: `apps/skill-manager/src/lib/api.ts`
- Create: `apps/skill-manager/src/components/SkillFilters.tsx`
- Create: `apps/skill-manager/src/components/SkillPool.tsx`
- Create: `apps/skill-manager/src/components/PublishQueue.tsx`
- Create: `apps/skill-manager/src/components/ConfirmActionDialog.tsx`
- Create: `apps/skill-manager/src/lib/queue.ts`
- Create: `apps/skill-manager/src/lib/queue.test.ts`

- [ ] **Step 1: Write failing pure queue tests.**

```ts
it("removing an item from the queue never changes deployment state", () => {
  const initial = [{ skillId: "macro", targets: ["openclaw"], deployment: "published" }];
  expect(removeQueueItem(initial, "macro")).toEqual([]);
  expect(initial[0].deployment).toBe("published");
});

it("keeps the two selected targets in one queue item", () => {
  expect(addQueueTarget([], "macro", "openclaw")).toEqual([
    { skillId: "macro", targets: ["openclaw"] },
  ]);
  expect(addQueueTarget([{ skillId: "macro", targets: ["openclaw"] }], "macro", "hermes")[0].targets)
    .toEqual(["openclaw", "hermes"]);
});
```

- [ ] **Step 2: Run tests and verify failure.**

Run: `cd apps/skill-manager && pnpm test -- --run src/lib/queue.test.ts`

Expected: FAIL because the workspace and queue helper do not exist.

- [ ] **Step 3: Implement the standalone UI.**

Configure `output: 'standalone'`, `basePath: '/skills'`, and the development rewrite from `/api/skills/:path*` to `http://localhost:8097/api/:path*` with `basePath: false`. In `page.tsx`, fetch cards through `api.ts`; keep filters and publish queue in client state. `SkillFilters` filters by free-text, source, tag, deployment state and update state. `SkillPool` adds a skill with explicit target chips. `PublishQueue` calls `/publish/plan`, presents `add/update/unchanged/blocked`, and never sends a mutation until `ConfirmActionDialog` supplies a password. Use the same dialog for registration, publish, rollback and unpublish; clear password state on close and on request completion.

- [ ] **Step 4: Make the UI build and queue tests pass.**

Run: `cd apps/skill-manager && pnpm install --frozen-lockfile && pnpm test -- --run src/lib/queue.test.ts && pnpm build`

Expected: PASS; build emits a standalone `.next/standalone` server.

- [ ] **Step 5: Commit the management workspace.**

Run: `git add apps/skill-manager && git commit -m "feat(skill-manager): 新增双栏发布工作台"`

## Task 7: Wire the new service into NAS deployment

**Files:**

- Modify: `docker-compose.nas.yml`
- Modify: `nginx/web.conf`
- Modify: `scripts/deploy-nas.sh`
- Create: `scripts/start-skill-manager-dev.bat`
- Modify: `.gitignore`
- Modify: `CLAUDE.md`
- Modify: `DOCKER_DEPLOY.md`
- Create: `docs/skill-manager-nas-setup.md`

- [ ] **Step 1: Add failing/static deployment assertions.**

```python
def test_compose_exposes_only_fixed_skill_manager_mounts(compose_text: str):
    assert "/var/run/docker.sock" not in compose_text
    assert "${SKILLS_SOURCE_HOST_PATH}:" in compose_text
    assert "${OPENCLAW_SKILLS_HOST_PATH}:" in compose_text
    assert "${HERMES_SKILLS_HOST_PATH}:" in compose_text
```

Put this in `backend/skill-manager/tests/test_deployment_files.py`, reading repository files relative to the test file.

- [ ] **Step 2: Run the assertion and verify failure.**

Run: `cd backend/skill-manager && uv run pytest tests/test_deployment_files.py -v`

Expected: FAIL because Compose has no skill-manager mounts or routes.

- [ ] **Step 3: Add Compose, Nginx, deploy-script, and documentation integration.**

Add backend `skill-manager-backend` on port `8097` and frontend `skill-manager-frontend` on port `3008`; add them to `deploy-nas.sh` target validation, `get_services`, `all`, and `get_buildx_config`. Add two Nginx upstreams, the `/skills/_next/static/`, `/skills`, and `/api/skills/` three-piece route set, plus root page link. Bind mount only these host variables into backend:

```yaml
volumes:
  - ${SKILLS_SOURCE_HOST_PATH}:/mnt/skills-source:rw
  - ${GITHUB_SKILL_CACHE_HOST_PATH}:/mnt/github-skill-cache:rw
  - ${OPENCLAW_SKILLS_HOST_PATH}:/mnt/targets/openclaw:rw
  - ${HERMES_SKILLS_HOST_PATH}:/mnt/targets/hermes:rw
  - skill-manager-state:/app/state
```

Set backend path environment variables to those container paths, pass `SKILL_MANAGER_ADMIN_PASSWORD` only to the backend, and document NAS prerequisites: clone `ohyes768/skills`, create cache/state directories owned by the compose user, fill actual host paths and password in ignored `.env`, and configure Skills repo write credentials only if registry push is enabled. Do not put a secret in code, docs examples, or frontend build arguments.

- [ ] **Step 4: Run static deployment checks.**

Run: `cd backend/skill-manager && uv run pytest tests/test_deployment_files.py -v && docker compose -f ../../docker-compose.nas.yml config --quiet && bash ../../scripts/deploy-nas.sh --help >/dev/null && docker run --rm -v "${PWD}/../../nginx/web.conf:/etc/nginx/conf.d/web.conf:ro" nginx nginx -t`

Expected: PASS. If Docker is unavailable locally, run the first two static checks and perform the Compose/Nginx commands on NAS before rollout.

- [ ] **Step 5: Commit the NAS onboarding.**

Run: `git add docker-compose.nas.yml nginx/web.conf scripts/deploy-nas.sh scripts/start-skill-manager-dev.bat .gitignore CLAUDE.md DOCKER_DEPLOY.md docs/skill-manager-nas-setup.md backend/skill-manager/tests/test_deployment_files.py && git commit -m "feat(skill-manager): 接入 NAS 部署链路"`

## Task 8: End-to-end verification and operational handoff

**Files:**

- Modify: `backend/skill-manager/tests/test_api.py`
- Modify: `docs/skill-manager-nas-setup.md`
- Modify: `.trellis/tasks/09-20-skill-publish-console/prd.md`

- [ ] **Step 1: Add one end-to-end test covering the protected publish journey.**

```python
def test_registered_github_skill_can_be_planned_published_and_rolled_back(
    client, github_fixture, configured_roots
):
    scanned = client.post("/api/skills/github/scan", json={"repository": github_fixture.url}).json()
    registered = client.post("/api/skills/github", json={
        "password": "correct", "repository": github_fixture.url,
        "path": scanned["candidates"][0]["path"], "name": "Fixture", "tags": ["test"],
    }).json()
    plan = client.post("/api/skills/publish/plan", json={"items": [{"skill_id": registered["id"], "targets": ["openclaw"]}]}).json()
    assert plan["items"][0]["action"] == "add"
    assert client.post("/api/skills/publish", json={"password": "correct", "items": plan["items"]}).status_code == 200
    assert (configured_roots.openclaw / registered["id"]).is_symlink()
    assert client.post(f"/api/skills/{registered['id']}/targets/openclaw/rollback", json={"password": "correct"}).status_code in {200, 409}
```

- [ ] **Step 2: Run the complete local quality gate.**

Run: `cd backend/skill-manager && uv run pytest tests -v && cd ../../apps/skill-manager && pnpm test -- --run && pnpm build && cd ../.. && docker compose -f docker-compose.nas.yml config --quiet && bash -n scripts/deploy-nas.sh`

Expected: all tests and static configuration commands PASS.

- [ ] **Step 3: Validate NAS staging with real but non-destructive inputs.**

Run on NAS: `./scripts/deploy-nas.sh skill-manager both --no-pull && curl -fsS http://127.0.0.1:8097/api/health && ./scripts/deploy-nas.sh nginx`

Expected: health returns `{"status":"ok"}`; Nginx reload succeeds; `/skills` renders; a plan preview performs no filesystem mutation.

- [ ] **Step 4: Update the PRD acceptance checklist with evidence and commit.**

For every checked acceptance criterion, add the exact test command or NAS validation date to `prd.md`; leave any unavailable NAS-only evidence unchecked. Then run:

Run: `git add backend/skill-manager/tests/test_api.py docs/skill-manager-nas-setup.md .trellis/tasks/09-20-skill-publish-console/prd.md && git commit -m "test(skill-manager): 验证发布全链路"`

## Final verification checklist

- [ ] `backend/skill-manager`: full pytest suite passes.
- [ ] `apps/skill-manager`: queue test suite and production build pass.
- [ ] `docker compose -f docker-compose.nas.yml config --quiet` passes.
- [ ] `bash -n scripts/deploy-nas.sh` passes and `skill-manager` appears in help, target mapping, all-service mapping and buildx mapping.
- [ ] Nginx configuration test passes before reload.
- [ ] NAS health check returns 200 and UI loads at `/skills`.
- [ ] Publishing a test Skill proves a valid Linux symlink lands only in the selected target root; wrong password, ordinary directory conflict, invalid GitHub URL, traversal attempt and rollback each produce the documented result.
