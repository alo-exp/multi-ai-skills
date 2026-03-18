# Domain Knowledge: DevOps Platforms

## Evaluation Categories

When researching DevOps platforms, ensure coverage of these domain-specific capability areas (in addition to generic categories from the prompt template):

- CI/CD Pipeline Management
- Infrastructure as Code (IaC)
- Container Orchestration & Kubernetes
- Monitoring, Observability & AIOps
- DevSecOps & Supply Chain Security
- Incident Management & On-Call
- Configuration & Secret Management
- Artifact & Package Management
- GitOps & Deployment Strategies
- Developer Experience & Self-Service
- Platform Engineering & Internal Developer Platforms (IDP)
- Cloud Cost Management & FinOps
- Service Mesh & Networking
- Feature Flags & Progressive Delivery
- Environment Management & Provisioning

## Key Terminology

- **DORA metrics:** Deployment Frequency, Lead Time for Changes, Change Failure Rate, Mean Time to Recovery — the four key DevOps performance indicators
- **GitOps:** Operating model where Git is the single source of truth for declarative infrastructure and applications
- **Shift-left:** Moving testing, security, and quality checks earlier in the development lifecycle
- **SRE (Site Reliability Engineering):** Discipline applying software engineering to operations problems; focuses on SLOs, error budgets, toil reduction
- **Service mesh:** Infrastructure layer handling service-to-service communication (e.g., Istio, Linkerd)
- **Blue-green deployment:** Running two identical production environments; switching traffic between them for zero-downtime releases
- **Canary deployment:** Gradually rolling out changes to a small subset of users before full deployment
- **Feature flags:** Runtime toggles controlling feature visibility without code deployment
- **IDP (Internal Developer Platform):** Self-service layer abstracting infrastructure complexity for developers
- **Platform engineering:** Discipline of building and maintaining IDPs to improve developer productivity
- **Golden paths:** Opinionated, pre-configured templates that encode best practices for common development tasks
- **Software catalog:** Central registry of all services, APIs, and resources in an organization (e.g., Backstage catalog)
- **Scorecard:** Automated compliance/quality check applied to catalog entries to track engineering standards
- **RBAC:** Role-Based Access Control — assigning permissions based on organizational roles
- **OPA (Open Policy Agent):** Policy engine for unified policy enforcement across the stack
- **SBOM (Software Bill of Materials):** Inventory of all components in a software artifact for supply chain security
- **SAST/DAST:** Static/Dynamic Application Security Testing
- **SLO/SLA/SLI:** Service Level Objective/Agreement/Indicator — reliability targets and measurements
- **Toil:** Repetitive, manual operational work that scales linearly with service growth
- **BYOC/BYOK:** Bring Your Own Cloud / Bring Your Own Kubernetes — deployment models where the platform runs on customer-provided infrastructure

## Evaluation Criteria

When consolidating reports for DevOps platforms, weight these factors:

1. **Integration breadth and depth** — How many tools does the platform integrate with? Are integrations native or via generic webhooks? Does it support the major CI/CD tools (Jenkins, GitHub Actions, GitLab CI, CircleCI)?
2. **DORA metrics support** — Does the platform measure and surface the four DORA metrics? Can it track deployment frequency, lead time, change failure rate, and MTTR?
3. **Security posture** — Does it include supply chain security (SBOM, vulnerability scanning), secrets management, policy enforcement (OPA/Rego), and compliance frameworks?
4. **Self-service developer experience** — Can developers provision environments, deploy services, and access resources without filing tickets? Are there golden paths/templates?
5. **Enterprise governance** — RBAC, audit trails, SSO/SAML, multi-tenancy, cost controls, approval workflows
6. **Kubernetes-native capabilities** — Does it support Kubernetes natively? Helm charts, operators, CRDs, multi-cluster management?
7. **Observability integration** — Does it connect to monitoring tools (Prometheus, Grafana, Datadog, New Relic)? Does it provide built-in dashboards?
8. **GitOps support** — Does it use Git as the source of truth for infrastructure and deployments? ArgoCD, Flux integration?
9. **Extensibility** — Plugin/extension model, API completeness, custom resource support, webhook/event system
10. **Multi-cloud support** — Does it work across AWS, Azure, GCP, and on-premise? Or is it locked to a single cloud?

---

## Platform Archetypes

Use these archetypes to calibrate expected tick counts and identify strong/weak categories when mapping a new platform.

| Archetype | Examples | Expected strong categories | Expected weak/zero categories | Expected tick count |
|---|---|---|---|---|
| **Full Kubernetes platform** | OpenShift, Rancher, KubeSphere | 1-4, 10, 11 | 14 | ~250-280 |
| **CI/CD-focused platform** | CloudBees, GitLab CI, Jenkins | 6, 8, 10, 16 | 2, 3, 4, 15 | ~80-100 |
| **SDLC Suite** | Azure DevOps, GitHub Enterprise | 1, 6, 8, 10, 14, 16 | 2, 3, 4, 7, 11, 12, 13, 15 | ~90-110 |
| **Internal developer portal** | Port, Backstage, Humanitec | 9, 16 | 2, 3, 4, 6 | ~40-55 |
| **PaaS / app deployment** | Qovery, Epinio, Heroku | 1, 6, 8, 9 | 3, 4, 13, 14 | ~65-85 |
| **PaaS / IDP (K8s-native)** | Northflank | 1 (partial), 2 (partial), 4 (partial), 5, 6, 8, 9, 10, 11, 16, 17, 18 | 3 (beyond TLS/domains), 7, 12, 13, 14, 15, 19, 20 | ~120-140 |
| **Cloud cost / FinOps** | Harness CCM | 15 | Most others | ~40-55 |
| **Enterprise DevSecOps / Release Orchestration** | Digital.ai | 8, 10, 14, 16 | 1-4, 7, 15 | ~100-120 |

**Coverage calibration:** A CI/CD-focused platform scoring ~90 ticks (vs. ~270 for a full K8s platform) is expected and correct — not a sign the mapping was incomplete. Zero ticks in infrastructure provisioning, networking, scaling, or cost management is the right outcome for platforms that don't operate in those domains. Do not force-tick features in categories where the platform has no presence.

**PaaS/IDP (K8s-native) note:** Platforms like Northflank that combine PaaS simplicity with IDP depth represent a hybrid category. They feature broader Kubernetes controls, multi-cloud BYOC/BYOK support, managed databases, and enterprise security capabilities. They excel in developer experience, deployment orchestration, and multi-tenancy while maintaining abstraction over low-level networking and cost management.

**SDLC Suite note:** Platforms like Azure DevOps that combine planning, source control, CI/CD, testing, and package management. Strong in categories 1 (architecture/administration), 6 (CI/CD), 8 (testing/release), 10 (security compliance), and 14 (project management). Typically zero coverage in infrastructure, networking, scaling, observability, cost management, and K8s-specific features.

---

## Inference Patterns

### Auth-backbone inference

When a platform delegates authentication to a well-known identity provider (e.g., Azure AD/Entra ID, Okta, Google Cloud Identity), and the CIR confirms the delegation mechanism, you may infer that authentication standards (SAML, OIDC, MFA) are supported via the IdP backbone without explicit name-checking for each protocol. Document this as "auth-backbone inference" in your mapping comments.

**Conditions for applying:**
1. The CIR explicitly names the IdP or identity mechanism
2. The IdP is a well-established, widely-known service with documented standards compliance
3. The matrix feature asks for a capability (e.g., "SAML 2.0 / OIDC / MFA") that is universal to that IdP class

**Example:** Azure AD confirms authentication/authorization; assume SAML/OIDC/MFA via AD standards → tick "Authentication: SAML 2.0 / OIDC / MFA"

### Compliance certification inference

When a CIR claims broad compliance (e.g., "100+ compliance certifications"):
- **Tick** if the certification is universally included in the platform's compliance portfolio across all standard deployments (e.g., SOC 2, GDPR, ISO 27001, HIPAA for major cloud platforms)
- **Do NOT tick** if the certification is only available in a separate government-specific deployment (e.g., FedRAMP in GovCloud only) unless the CIR explicitly confirms it applies to the primary deployment
- When in doubt, check the platform's compliance documentation; if a certification requires a separate product SKU or regional variant, don't infer it for the standard platform

**Example:** Azure states "100+ certifications" but FedRAMP is GovCloud-only → tick SOC 2/GDPR/ISO 27001/HIPAA (universally included), don't tick FedRAMP (government-specific variant)

### Networking abstraction caveat for PaaS/IDP

PaaS and IDP platforms abstract away most networking complexity. When evaluating:
- **Typically supported:** TLS/SSL termination, custom domain names, basic load balancing, automatic certificate management
- **Typically NOT supported:** Specific ingress controller implementations (NGINX Ingress), service meshes (Istio, Linkerd), DNS provider integrations (Route 53, Cloudflare DNS), advanced network policies (eBPF/Cilium/Calico), VPC/network segmentation, multi-cluster networking

Do not force-tick networking features based on "the platform does networking." Look for explicit CIR evidence. If a feature row specifies a particular tool (e.g., "Ingress controller (NGINX-based)") or advanced networking control, verify the CIR specifically mentions it.

### Functional equivalence

If the matrix row describes a capability by referencing a specific tool (e.g., "Policy-as-code enforcement (OPA-based)") but the platform achieves the same outcome with a different tool (e.g., Kyverno, or YAML/Groovy pipeline policies), tick it. The matrix tracks capabilities, not specific tool choices. The tools must be genuinely equivalent in what they deliver to end users.

### Optional vs. default features

When the matrix feature name includes qualifiers like "as platform default" (e.g., mTLS "as platform default"), the CIR evidence must confirm that qualifier. However:
- If a CIR marks a feature as "optional" (wrench emoji), the capability EXISTS even if not default-on — tick it
- The matrix tracks capability existence, not default-on status
- Document the difference in mapping comments when relevant

**Example:** Matrix feature "mTLS (as platform default)". CIR says "mTLS support (optional, must be enabled)". Tick the feature because mTLS exists in the platform.

---

## CIR Evidence Rules

### Variant A — Standard CIR with status markers

Has a narrative overview organized by functional area, followed by a "Capabilities & Features Checklist" section with status markers per item. Both sections are platform-specific evidence.

| CIR Status | Symbol | Tick? | Rationale |
|---|---|---|---|
| **Core** | ✅ | **Yes** | Foundation of the platform, clearly supported |
| **Optional** | 🔧 | **Yes** | Available as an add-on — the capability exists even if not default-on |
| **Claimed but Unverified** | ⚠️ | **No** | Marketing claim without published implementation details |
| **Not Documented** | ❌ | **No** | No evidence in public sources |

When a CIR marks something as ⚠️ claimed-but-unverified, resist the temptation to tick it. The matrix reflects what a platform demonstrably does, not what it claims to do.

### Variant B — Detailed Capability Report with product-agnostic checklist

Has detailed narrative capability analysis (Sections 2.x), followed by a standalone "Capabilities & Features Checklist" that is explicitly product-agnostic — a generic feature taxonomy for benchmarking, with NO status markers and NO platform-specific assessments. Items are organized into Capability Groups using unchecked item format. An "Assumptions & Gaps" table may provide secondary evidence with explicit markers (⚠️ Partial, ❌ Unresolved).

**Critical rule:** The product-agnostic checklist section MUST NOT be used as evidence for tick decisions.

| Evidence Source | Tick? | Rationale |
|---|---|---|
| Clear description in narrative of how the platform implements the capability | **Yes** | Confirmed feature with implementation details |
| Assumptions/Gaps table marks the item as confirmed | **Yes** | Explicit positive confirmation |
| Assumptions/Gaps table marks the item ⚠️ Partial | **No** | Partially implemented or partially confirmed |
| Assumptions/Gaps table marks the item ❌ Unresolved | **No** | Explicitly unresolved |
| Narrative says "not confirmed" / "not fully confirmed" / "depth not confirmed" | **No** | Insufficient evidence |
| "Announced intent" / "planned" / "roadmap" | **No** | Future capability, not current |
| Capability described only via third-party plugins | **Case-by-case** | If plugin is part of standard supported ecosystem, tick. If community-only without support confirmation, don't. |

### Variant identification

Look for explicit disclaimers like "Product-agnostic feature hierarchy for competitive benchmarking." If present, the checklist is Variant B and evidence-free. Also check whether checklist items have status markers — if they don't, it's Variant B. In Variant B, look for Capability Groups (non-numbered categorical headings) as organizational structure.

### Scanning both sections

- **Variant A:** The Checklist section provides structured lists, but narrative sections often contain critical specificity the checklist omits (specific DNS providers, exact external secrets stores, alerting channels, build system details, RBAC scope). Treat both sections as required reading.
- **Variant B:** Only narrative sections constitute primary evidence. The product-agnostic checklist may list capabilities the platform does NOT have. Always verify against narrative text.

---

## Matrix Categories (Lifecycle Order)

The comparison matrix uses 20 numbered categories ordered by platform evaluation lifecycle:

| # | Category | Lifecycle Phase |
|---|----------|----------------|
| 1 | Core Architecture & Deployment Model | Foundation |
| 2 | Infrastructure Provisioning & Cloud Management | Foundation |
| 3 | Networking & Traffic Management | Foundation |
| 4 | Scaling & Performance | Foundation |
| 5 | Configuration & Standards Management | Build / Deliver |
| 6 | CI/CD & Build Automation | Build / Deliver |
| 7 | Artifact & Package Management | Build / Deliver |
| 8 | Application Deployment & Release Management | Build / Deliver |
| 9 | Developer Self-Service & Experience | Build / Deliver |
| 10 | Security & Compliance | Operate |
| 11 | Observability & Monitoring | Observe |
| 12 | Chaos Engineering, Resilience & Feature Delivery | Operate |
| 13 | AI & Intelligent Automation | Operate |
| 14 | Planning & Project Management | Platform |
| 15 | Cloud Cost Management & FinOps | Platform |
| 16 | Integrations & Ecosystem | Platform |
| 17 | Deployment Models & Reliability | Governance |
| 18 | Packaging, Support & Commercial Model | Governance |
| 19 | Market Recognition & Social Proof | Governance |
| 20 | Software Distribution & Tenant Management | Governance |

---

## CIR-to-Matrix Category Cross-Reference

| CIR Checklist Section (typical) | Matrix Categories (likely matches) |
|---|---|
| Application Deployment & Lifecycle | 8. App Deployment & Release; 4. Scaling & Performance |
| Multi-Tenancy & Team Management | 1. Core Architecture; 10. Security & Compliance |
| Networking & Service Mesh | 3. Networking & Traffic Management |
| Security & Compliance | 10. Security & Compliance; 11. Observability (audit logs) |
| Observability & Monitoring | 11. Observability & Monitoring |
| CI/CD & GitOps | 6. CI/CD & Build Automation; 8. App Deployment |
| Data & Storage | 2. Infrastructure Provisioning; 7. Artifact & Package Management |
| Platform Administration | 18. Packaging, Support & Commercial; 1. Core Architecture |
| Developer Experience | 9. Developer Self-Service & Experience; 15. Cloud Cost Management |
| Enterprise Features | 17. Deployment Models & Reliability; 18. Packaging, Support |

**Key insight:** Don't assume a CIR section maps to one matrix category. Read each CIR section while mentally scanning multiple matrix categories for matches.

---

## Common Feature Name Equivalences

Known mismatch patterns between CIR checklist names and matrix feature names:

| CIR Name | Matrix Name |
|----------|-------------|
| Deployment audit trail | Deployment audit log / history |
| Notification integration | Communication platform integration (Slack, Teams, etc.) |
| IaC: Ansible | IaC: Ansible (playbook execution via Stacks CRD...) |

Functional equivalence rules:
- "Policy-as-code enforcement (OPA-based)" ← Kyverno, YAML/Groovy pipeline policies also qualify
- "Pipeline-as-code (YAML-based definitions)" ← Jenkinsfile Declarative qualifies
- IaC = Infrastructure as Code
- Blue-green = Zero-downtime deployment (when implemented via traffic switching)

**Note:** "Prometheus metrics endpoint" and "Deployment approval workflow" may appear in CIR checklists but not as standalone matrix rows. Map them to the nearest equivalent matrix feature.

---

## New Row Guidelines

### Conservatism for mature matrices

In a matrix with 490+ features across 20 categories, most capabilities from a new platform — especially one built on standard CNCF tools (Argo CD, Istio, Prometheus, Grafana, etc.) — will already have matching rows. **Zero new rows is a valid and expected outcome**, not a sign the mapping was incomplete.

### New row criteria

For each proposed new capability:
1. Confirm it is a **genuine user-facing capability** — something end users directly interact with or benefit from. Do NOT add internal implementation details, data flow mechanisms, or architecture patterns as standalone features.
2. Decide which existing category it belongs to (or create a new category if none fits)
3. Assign a priority: Critical / Very High / High / Medium / Low
4. Determine ticks for ALL existing platforms (not just the new one) by scanning their CIRs if available

### Row ordering within categories

Features within each category should follow a logical grouping:
1. Foundational/core capabilities first
2. Related features grouped together (sub-themes)
3. Within sub-groups, general then specific
4. Higher priority as tiebreaker within sub-groups
5. Platform-specific/niche features at the end

---

## Tick Verification Approach

1. Extract per-platform tick/untick lists from the matrix
2. For each platform, read its CIR and check every ticked feature for clear evidence of support
3. Flag false positives (ticked but CIR doesn't support) and false negatives (unticked but CIR confirms)
4. Be conservative — only flag clear mismatches. When in doubt, assume the tick is correct.
5. For platforms without CIRs, use web search for independent verification
6. Apply corrections in a new version, preserving the old version unchanged

---

## Priority Weights

| Priority | Weight |
|----------|--------|
| Critical | 5 |
| Very High | 4 |
| High | 3 |
| Medium | 2 |
| Low | 1 |

Score = sum of (weight * tick) across all features for a platform column. COUNTIFS formula with "?*" wildcard pattern (not SUMPRODUCT+LEN which fails with inlineStr).
