# Hermes profile contracts

## 1. Scope / Trigger

Changing configured installation targets, publishing, install preview/execution, target classification, startup migrations or registry/cache removal.

## 2. Signatures

- `GET /api/skills/install-targets` -> `{items:[{id,provider,profile_name,name,install_path,configured,available,unavailable_reason}]}`.
- `POST /api/skills/install/preview`: exactly one of `skill_ids`, `items:[{skill_id,targets}]`, or `scan_task_id + candidates`; optional `target_ids` for IDs/candidates. Candidate `targets` optionally overrides the batch selection for exact failure retry.
- Preview returns `plan_id`, pair-level `items` (including target), `affected_installations:[{skill_id,name,target}]`, and `expires_in`.
- Execute keeps `{plan_id,request_id,password}`; background results include target. Old publish/plan/unpublish routes accept profile IDs too.
- SQLite `install_target(id,provider,profile_name,name,last_root)` complements unchanged deployment/history keys. Old database gets a `.before-hermes-profiles` backup before additive schema migration.

## 3. Contracts

`SKILL_MANAGER_HERMES_TARGETS` legacy bootstrap JSON array entries contain `id,name,profile_name,skills_root`. `hermes` preserves legacy identity; named IDs use `hermes:profile:<slug>`. Absent/empty environment variable uses legacy HERMES_SKILLS_ROOT; explicit `[]` is invalid. Config roots are absolute, unique, non-overlapping and separate from sources/cache/state; missing target directories degrade individually without mkdir.

TargetResolver owns fixed deployment path authorization and captures canonical roots. Managed profile settings are now persistent/live after the one-time UI migration below; unmanaged catalog metadata never authorizes old roots. A root change with active records fails initialization. Classification uses is_install_target, including unavailable namespaced profiles, never a fixed set complement.

Plan limits: 100 Skills, 20 unique targets, 500 pairs; duplicates of a pair deduplicate. Validate all target IDs and availability before scan/source preparation. Source fingerprints are per Skill, target fingerprints include root path/device/inode and link state, affected installations include unselected and inaccessible active profiles. Recheck before submission and each write; changes require new preview. Lock confirmed checkout and target writes together. Registry upsert is once per new Skill; shared repository checkout is reused; conflicts remain pair-local.

Multi-profile links share live source content. Checkout updates siblings' expected source hash/revision only after the confirmed HEAD is observed, including when a deleted member fails validation. Removed members fail independently. Unpublish deletes only that target's managed link. Active unavailable records block registry/cache deletion. Startup offline migration only republishes recorded, available profile links; export and new profile links are untouched.

## 4. Validation & Error Matrix

| Condition | Result |
| --- | --- |
| Duplicate/overlapping roots, bad ID or relative path | Settings validation error |
| Active ID changes canonical root | Initialization fails with original root |
| Unknown/unavailable target | 400 target_unavailable before source work |
| Empty targets, mixed modes, excess pairs | 400 invalid_request |
| Target root/link/source/impact set changes | 409 stale_plan |
| Wrong password | 401 invalid_password; no execution |
| Ordinary target occupant or escaping link | Pair blocked; other pairs proceed |
| Missing/expired plan or restarted task | 410 plan_expired / 404 task_not_found |
| Active configured or offline profile on source deletion | 409 skill_active |
| Profile target on export/delete-export | 400 invalid_target_kind |

## 5. Good / Base / Bad Cases

Good: one Skill links into two directories, one conflict retries only its pair, one unpublish leaves the other link and source intact.
Base: no JSON keeps legacy hermes directory/rows/history; adding a profile creates only catalog metadata.
Bad: reinterpreting offline profile rows as export, restoring write access from last_root, accepting a new root with an old plan, or repeating registration per target.

## 6. Tests Required

`tests/test_profiles.py`: two/three targets, real dual links and independent unpublish, conflicts/exact retry, candidate registration once, shared checkout once/all-profile impact, source/root/link/impact invalidation, password/idempotence, missing roots, retained offline records and config validation.
Existing full backend suite must remain green, especially direct-cache removed-member tests, export, legacy migration and retired OpenClaw behavior.

## 7. Wrong vs Correct

Wrong: `record.target not in LINK_TARGET_IDS` means export, or parse profile IDs through TargetKey enum.
Correct: classify using `is_install_target(record.target)` and resolve writes only through Publisher.targets. Persistent metadata provides display/history only.

## 部署挂载调整（2026-10-14 用户确认）

Compose 一次性同路径读写挂载默认 skills 与 profiles 父目录：`HERMES_SKILLS_HOST_PATH` 缺省 `/home/ohyes768/.hermes/skills`，`HERMES_PROFILES_HOST_PATH` 缺省 `/home/ohyes768/.hermes/profiles`。两项 long bind 均设置 `create_host_path:false`，宿主目录缺失直接失败；HERMES_SKILLS_ROOT 使用与默认 skills mount 完全相同的变量/缺省值。

用户明确接受父目录挂载扩大容器可见范围；管理接口仍只按配置授权的 skills 目录写入。这个部署调整不自动登记/发现新目标，不改变 Settings/env 目标真源；网页目标 CRUD 仍在独立 planning 任务中。profiles 根下新增目录无需增加挂载；父目录外的目标仍需单独授权和可达目录。

验证：使用独立临时 env 文件运行 `docker compose config --format json`，确认缺省及用户 override 的 source/target 一致、rw、host path 不自动创建和后端根一致。无需启动服务或读真实 `.env`。compose 输出可能省略 false 字段，校验以缺省 false 解释；源码显式保持 false。

## 界面维护目标（2026-10-14）

### 1. Scope / Trigger

目标配置CRUD、目录候选发现、DB迁移、resolver live lookup 和并发安装/删除。

### 2. Signatures

`GET /api/skills/install-targets/profiles` → profile_name/skills_path/available/unavailable_reason/existing_target_id。catalog 增加 editable/deletable/removed/active_installation_count/config_revision。POST install-targets `{profile_name,name,password}`；PATCH `/{id}` `{name,expected_revision,password}`；DELETE `/{id}` `{expected_revision,password}`。未知字段/null按模型拒绝，密码不strip、不持久化。

SQLite install_target 新增 managed(0)/removed_at('')/config_revision(1)，target_config_history追加成功配置操作及公开元数据。`install_targets_ui_v1` 标记一次性事务导入；老表加列前备份 `.before-target-ui`。

### 3. Contracts

Settings `SKILL_MANAGER_HERMES_PROFILES_ROOT` 是预先授权父根，与 compose HERMES_PROFILES_HOST_PATH 相同。候选只能是直接子目录的实际 skills，默认 hermes 只读；无父根的旧部署只保留明确配置的 legacy 安装，不能网页新增。父根存在时旧 named 根越界则保留unmanaged/offline记录，不变更链接。

网页 profile 配置存 DB，启动env只首次导入，不能覆盖改名或复活软删除。历史 catalog 缺省managed=0，不授予写权限；删除保留identity和台账，同profile恢复原ID。显示名可改，目录/profile/ID不可改。默认原根变更阻止，不能重映射存量身份。

CRUD、legacy publish/unpublish、安装source preparation与链接写共用operation_lock；seed、CRUD在BEGIN IMMEDIATE重读版本/active并审计。Resolver每次root/fingerprint重读DB，包含config revision、删除/授权状态。worker取得锁后在checkout/registration前复验target fingerprint，防止start与worker间删除获锁后仍准备来源。

### 4. Validation & Error Matrix

- 缺父根/skills、无权限、profile名逃逸、profile或skills重定向：400 target_unavailable，无mkdir。
- default修改/删除：400 reserved_target；空显示名/未知字段/null：400 invalid_request。
- 重复live目标：409 target_exists；过期revision：409 target_changed；active（含异常/离线）：409 target_in_use。
- 不可编辑/删除/历史unknown目标：404 target_not_found；原错误密码401无配置或审计副作用。
- 配置改变后的安装计划：409 stale_plan；worker中途获锁复验失败按对应组合blocked，其他健康组合可继续。

### 5. Good / Base / Bad Cases

Good：新增已有profile → 即时安装 → active删除被拒 → 正常下架 → 软删除 → 重启不复活 → 同profile恢复原ID。
Base：旧无父根部署仍用已配置旧目标安装；catalog历史不会自动成为授权。
Bad：用last_root恢复历史权限，env每次启动重种目标，config删除后异步worker继续checkout/写active。

### 6. Tests Required

test_target_ui.py覆盖候选/CRUD、错误密码/default、符号链接逃逸、env不覆盖、软删恢复、活跃/异常链接阻止、DB旧表备份与安装删除竞态。test_profiles.py新配置修改经DB/API，env追加不会再次seed。
InstallTargetManager.test.ts覆盖默认只读、新增确认一次、active删除跳看板、revision冲突与候选失败禁止提交。全量backend/frontend、类型/lint/build、真实目录symlink及浏览器模拟分别记录。

### 7. Wrong vs Correct

Wrong：在构造时缓存configured dict，或者每次启动sync env覆盖DB。
Correct：一次性受信任seed，操作时live读取managed/tombstone/revision，并复验固定父根及冻结skills路径。
