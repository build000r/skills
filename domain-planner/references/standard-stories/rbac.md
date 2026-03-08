# Standard Stories: RBAC & Auth Patterns

> Reusable RBAC and auth user story templates for any domain. When a new slice touches roles, permissions, feature gating, or access control, use these as starting points in Phase 1 Discovery.

## How to Use

During Phase 1, check: "Does this slice involve any of these patterns?"
- If yes, copy relevant stories and adapt role names / resource names
- If the slice is auth-adjacent (e.g., needs feature gating), pull just that section
- Skip stories that don't apply — these are a menu, not a mandate
- Keep this file generic. Put project-specific role names, portals, and business examples in mode files or slice-specific planning docs.

---

## 1. Role Hierarchy & Assignment

Standard stories for any multi-role system with per-resource scoping.

**Adapt:** Replace `organization` with your resource type, replace role names with your hierarchy.

### Core Stories

- [ ] **Admin can manage users across the system** — CRUD user records, view all users
- [ ] **Admin can assign roles per {resource}** — Flexible scoping (e.g., per organization, per team)
- [ ] **Admin can revoke roles with audit trail** — Soft revocation preserves history
- [ ] **Admin can view role change history** — Audit compliance via event trail
- [ ] **Higher roles inherit lower role permissions** — A higher role implicitly satisfies lower-role checks

### Role Isolation Stories

- [ ] **{Role A} can access only their assigned {resource}'s data** — Prevents data leakage between resources
- [ ] **{Role B} cannot access {Role A}'s data** — Privacy and isolation enforcement
- [ ] **Users with no active roles see empty state** — Pending users get helpful guidance, not errors

### Key Decisions to Resolve

| Decision | Options | Recommendation |
|----------|---------|----------------|
| Role storage | Dedicated table vs entitlements | Entitlements if you have one; new table otherwise |
| Hierarchy model | Linear (admin > editor > viewer) vs DAG | Linear for most apps |
| Multiple users per role | One user per role per resource vs many | Many — teams need it |
| Role changes | Update in place vs revoke + create | Revoke + create for audit trail |
| One role per user per resource? | Single role vs multiple roles | Single — hierarchy makes multiple unnecessary |

---

## 2. Feature Flags (Two-Layer)

Standard stories for system-level kill switches + per-resource feature toggles.

### Core Stories

- [ ] **Admin can enable/disable features per {resource}** — Customized feature availability and rollout
- [ ] **Admin can toggle system-wide kill switches** — Global override for maintenance, debugging, staged rollouts
- [ ] **Admin always bypasses kill switches** — Admin access is never blocked by feature flags
- [ ] **Kill switch overrides {resource} toggle** — System off means off for everyone (except admin)
- [ ] **Feature state propagates within acceptable latency** — Define cache TTL (e.g., 5 min acceptable for v1)

### Resolution Order

```
Is system kill switch OFF?  → Hidden for everyone (admin bypasses)
Is {resource} toggle OFF?   → Hidden for this {resource}
Does user meet role minimum? → Hidden if role too low
All checks pass             → Show feature
```

### Key Decisions to Resolve

| Decision | Options | Recommendation |
|----------|---------|----------------|
| Feature storage | Entitlements, JSONB column, config service | Entitlements for audit trail |
| Cache TTL | Instant (WebSocket) vs 1min vs 5min | 5min for v1 (admin ops are rare) |
| Default state for new features | On or off | Off — explicit opt-in is safer |
| Feature key naming | `feature_name` vs `namespace:feature_name` | Namespaced (e.g., `workspace:feature:reports_dashboard`) |

---

## 3. Portal Routing & Role-Based Navigation

Standard stories for multi-portal apps where different roles see different UIs.

### Core Stories

- [ ] **Landing page reads user context and redirects to correct portal** — `/me` → role → portal route
- [ ] **Wrong-portal access redirects gracefully** — Member visiting an admin URL gets sent to the correct portal, not 403
- [ ] **Navigation is scoped by role** — Admin sees all nav items, end users see only what they need
- [ ] **Shared components work across portals** — Same `AttachmentUploader` in onboarding and member portals

### Portal Shell Pattern

Every portal page wraps in a shell that handles:
1. **Role guard** — redirect if wrong portal
2. **Navigation config** — role-specific menu items
3. **Layout** — consistent header, nav, main content area

```
<PortalShell role="{role}" nav="{full|standard|minimal|none}">
  <FeatureContent />
</PortalShell>
```

### Nav Variants

| Portal | Nav Variant | Contents |
|--------|-------------|----------|
| Admin | `full` | All sections, all portals, system settings |
| Power user | `standard` | Dashboard, tools, reports |
| End user | `standard` | Dashboard, documents, reports |
| Onboarding | `minimal` | Logo, workspace name, logout only |

### Key Decisions to Resolve

| Decision | Options | Recommendation |
|----------|---------|----------------|
| Portal per role vs shared portals | Separate route per role vs shared with conditionals | Separate — cleaner boundaries |
| Wrong-portal behavior | 403 page vs redirect | Redirect — better UX |
| Shared components location | Each portal copies vs shared directory | Shared `widget-primitives/controls/` |

---

## 4. Limited-Access Onboarding Flow

Standard stories for invited or pre-activated users who need limited access before becoming full users.

### Core Stories

- [ ] **{Operator/Admin} can create a pending {resource}** — Pre-activation entity without full system access
- [ ] **{Operator/Admin} can create a pending user** — Link email, issue entitlement before signup
- [ ] **Pending user can self-serve onboarding tasks** — Upload documents, answer questionnaires, complete setup
- [ ] **Pending user cannot access full-product features** — Zero access to protected data, tools, reports
- [ ] **Pending user cannot see internal rules or protected configuration** — Operators control what pending users see
- [ ] **{Operator/Admin} can activate pending user into a full role** — Revoke pending role, assign real role, update status
- [ ] **Activated user retains onboarding data** — Documents and progress carry over

### End-to-End Flow

```
1. Operator creates pending {resource} (status: pending)
2. Operator creates pending user (links email)
3. Operator assigns pending role (scoped to {resource})
4. Operator sends onboarding link (manual v1, automated v2)
5. Pending user signs up and claims entitlements
6. Pending user accesses limited portal (uploads, forms, setup tasks)
7. Operator/Admin activates pending user → full role
8. Next login redirects to full portal
```

### Key Decisions to Resolve

| Decision | Options | Recommendation |
|----------|---------|----------------|
| Pending role in role hierarchy? | Part of hierarchy vs separate branch | Separate — activation is a business decision, not permission escalation |
| Onboarding link delivery | Automated email vs manual | Manual for v1, automated for v2 |
| Data continuity on activation | Reset vs carry over | Carry over — same resource, different role |
| Multiple pending users per resource | One contact vs many | Many — multiple stakeholders in onboarding |

---

## 5. Admin Bootstrapping

Standard stories for first-user setup and system initialization.

### Core Stories

- [ ] **First admin is bootstrapped via direct DB flag** — No chicken-and-egg problem
- [ ] **Admin can grant admin to other users** — System grows beyond the bootstrap user
- [ ] **Admin detection works across auth layers** — Both app-specific and auth-layer admin checks

### Bootstrap Pattern

```sql
-- One-time bootstrap (run manually or via seed script)
UPDATE user_profiles SET is_admin = true WHERE email = 'admin@example.com';
```

### Key Decisions to Resolve

| Decision | Options | Recommendation |
|----------|---------|----------------|
| Admin flag location | Auth layer vs app layer vs both | App layer for speed, auth layer for cross-app |
| Multi-admin support | Single admin vs multiple | Multiple from day 1 — bus factor |
| Super-admin vs admin | One tier vs two | One tier for v1, add super-admin if needed |

---

## 6. Separate-Branch Roles (Non-Hierarchical)

Standard stories for roles that exist outside the linear hierarchy (e.g., support, moderator).

### Core Stories

- [ ] **{Branch role} has specific, limited capabilities** — Not above or below other roles
- [ ] **{Branch role} cannot access main hierarchy features** — Support staff cannot access protected admin features
- [ ] **{Branch role} shares portal shell with scoped navigation** — Reuses admin portal with restricted nav
- [ ] **`hasMinimumRole()` returns false for branch roles** — They're not in the hierarchy

### Key Pattern

```
HIERARCHY (linear):        BRANCHES (separate):
  Admin (4)                  Support
  Manager (3)                  ├── pre-activation workflow
  Member (2)                   └── NO protected admin features
  Viewer (1)
                             Moderator
                               ├── content review
                               └── NO admin features
```

---

## Checklist: Does My Slice Need RBAC Stories?

| If your slice... | Pull from section... |
|-----------------|---------------------|
| Adds a new user role | 1. Role Hierarchy, 6. Branch Roles |
| Needs admin-only features | 2. Feature Flags |
| Adds a new portal/page | 3. Portal Routing |
| Has limited-access onboarding users | 4. Limited-Access Onboarding Flow |
| Is the first slice in a new app | 5. Admin Bootstrapping |
| Needs feature toggles | 2. Feature Flags |
| Scopes data by organization/team/resource | 1. Role Isolation |
