# Standard Stories: RBAC & Auth Patterns

> Reusable user story templates extracted from `cfo_rbac`. When a new slice touches auth, roles, or access control, use these as starting points in Phase 1 Discovery.

## How to Use

During Phase 1, check: "Does this slice involve any of these patterns?"
- If yes, copy relevant stories and adapt role names / resource names
- If the slice is auth-adjacent (e.g., needs feature gating), pull just that section
- Skip stories that don't apply — these are a menu, not a mandate

---

## 1. Role Hierarchy & Assignment

Standard stories for any multi-role system with per-resource scoping.

**Adapt:** Replace `company` with your resource type, replace role names with your hierarchy.

### Core Stories

- [ ] **Admin can manage users across the system** — CRUD user records, view all users
- [ ] **Admin can assign roles per {resource}** — Flexible scoping (e.g., per company, per team)
- [ ] **Admin can revoke roles with audit trail** — Soft revocation preserves history
- [ ] **Admin can view role change history** — Audit compliance via event trail
- [ ] **Higher roles inherit lower role permissions** — Accountant implicitly passes client checks

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
Is company toggle OFF?      → Hidden for this company
Does user meet role minimum? → Hidden if role too low
All checks pass             → Show feature
```

### Key Decisions to Resolve

| Decision | Options | Recommendation |
|----------|---------|----------------|
| Feature storage | Entitlements, JSONB column, config service | Entitlements for audit trail |
| Cache TTL | Instant (WebSocket) vs 1min vs 5min | 5min for v1 (admin ops are rare) |
| Default state for new features | On or off | Off — explicit opt-in is safer |
| Feature key naming | `feature_name` vs `namespace:feature_name` | Namespaced (e.g., `cfo:feature:reports_dashboard`) |

---

## 3. Portal Routing & Role-Based Navigation

Standard stories for multi-portal apps where different roles see different UIs.

### Core Stories

- [ ] **Landing page reads user context and redirects to correct portal** — `/me` → role → portal route
- [ ] **Wrong-portal access redirects gracefully** — Client visiting admin URL gets sent to client portal, not 403
- [ ] **Navigation is scoped by role** — Admin sees all nav items, client sees minimal set
- [ ] **Shared components work across portals** — Same `DocumentUploader` in prospect and client portals

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
| Onboarding | `minimal` | Logo, company name, logout only |

### Key Decisions to Resolve

| Decision | Options | Recommendation |
|----------|---------|----------------|
| Portal per role vs shared portals | Separate route per role vs shared with conditionals | Separate — cleaner boundaries |
| Wrong-portal behavior | 403 page vs redirect | Redirect — better UX |
| Shared components location | Each portal copies vs shared directory | Shared `widget-primitives/controls/` |

---

## 4. Prospect / Onboarding Flow

Standard stories for pre-conversion users who need limited access before becoming full users.

### Core Stories

- [ ] **{Sales/Admin} can create a prospect {resource}** — Pre-conversion entity without full system access
- [ ] **{Sales/Admin} can create a prospect user** — Link email, issue entitlement before signup
- [ ] **Prospect can self-serve onboarding tasks** — Upload documents, answer questionnaires, view proposals
- [ ] **Prospect cannot access production features** — Zero access to financial data, tools, reports
- [ ] **Prospect cannot see internal pricing or logic** — Sales controls what prospect sees
- [ ] **{Sales/Admin} can convert prospect to full user** — Revoke prospect role, assign real role, update status
- [ ] **Converted user retains their onboarding data** — Documents and progress carry over

### End-to-End Flow

```
1. Sales creates prospect {resource} (status: prospect)
2. Sales creates prospect user (links email)
3. Sales assigns prospect role (scoped to {resource})
4. Sales sends onboarding link (manual v1, automated v2)
5. Prospect signs up and claims entitlements
6. Prospect accesses limited portal (uploads, proposals, Q&A)
7. Sales/Admin converts prospect → full role
8. Next login redirects to full portal
```

### Key Decisions to Resolve

| Decision | Options | Recommendation |
|----------|---------|----------------|
| Prospect in role hierarchy? | Part of hierarchy vs separate branch | Separate — conversion is a business decision, not permission escalation |
| Onboarding link delivery | Automated email vs manual | Manual for v1, automated for v2 |
| Data continuity on conversion | Reset vs carry over | Carry over — same resource, different role |
| Multiple prospects per resource | One contact vs many | Many — multiple stakeholders in onboarding |

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

Standard stories for roles that exist outside the linear hierarchy (e.g., sales, moderator).

### Core Stories

- [ ] **{Branch role} has specific, limited capabilities** — Not above or below other roles
- [ ] **{Branch role} cannot access main hierarchy features** — Sales can't see financial data
- [ ] **{Branch role} shares portal shell with scoped navigation** — Reuses admin portal with restricted nav
- [ ] **`hasMinimumRole()` returns false for branch roles** — They're not in the hierarchy

### Key Pattern

```
HIERARCHY (linear):        BRANCHES (separate):
  Admin (4)                  Sales
  Accountant (3)               ├── prospect management
  Client (2)                   └── NO financial data
  Employee (1)
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
| Has pre-conversion users | 4. Onboarding Flow |
| Is the first slice in a new app | 5. Admin Bootstrapping |
| Needs feature toggles | 2. Feature Flags |
| Scopes data by company/team | 1. Role Isolation |
