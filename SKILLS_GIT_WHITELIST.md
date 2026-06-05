# Skills Git Whitelist

This document outlines the criteria and approved list of skills suitable for inclusion in a git repository.

## Whitelist Criteria

A skill should be included in git if it meets **ALL** of the following criteria:

### 1. **Custom-made Reusable Knowledge** ✅
- Documents workflows, solutions, or established procedures
- Contains lessons learned, troubleshooting guides, or best practices
- Provides structured knowledge that would be lost if not persisted
- Not available in bundled hermes skills

### 2. **Infrastructure/Environment Specific** ✅
- Contains paths, configurations, or setup procedures specific to the current environment
- Documents system-specific workflows (e.g., M5 server setup, Vulkan GPU configuration)
- Preserves knowledge about unique infrastructure constraints

### 3. **No Sensitive Information** ✅
- No API keys, passwords, or secrets
- No personal identifiers or private information
- No sensitive configuration that shouldn't be public

### 4. **Well-Structured** ✅
- Proper YAML frontmatter with metadata
- Clear documentation of when/how to use
- Includes pitfalls and troubleshooting sections
- Has been tested and verified to work

### 5. **Self-Contained** ✅
- Minimal external dependencies (if any, they're documented)
- Doesn't rely on temporary session-specific data
- Can be used by other developers with similar setup

---

## Approved Skills for Git Inclusion

### Core System & Infrastructure

#### ✅ `router-troubleshooting` (mlops)
**Reason**: Documents critical infrastructure knowledge about m5-router service failures, INI parsing, and port conflicts. Contains specific troubleshooting steps that would be valuable for anyone running similar infrastructure.

**Git Value**: High - prevents repeated debugging of same issues, documents edge cases with llama.cpp router.

#### ✅ `model-manager` (mlops)
**Reason**: Documents the proxy architecture and model management system for Strix Halo APU. Contains important design decisions about memory management and model swapping.

**Git Value**: High - architectural documentation, troubleshooting guide, and API reference for the model management system.

#### ✅ `github-auth` (github)
**Reason**: Provides comprehensive authentication setup for GitHub workflows. Documents both HTTPS token and SSH key methods.

**Git Value**: Medium - standard GitHub setup procedures, but generic enough to be useful.

#### ✅ `openwebui-tool-management` (devops)
**Reason**: Documents the OpenWebUI plugin installation process and API usage for tool management.

**Git Value**: Medium - specific to the current OpenWebUI setup, but the API patterns are reusable.

### Project-Specific Knowledge

#### ✅ `algotrading-agent-army-resume` (data-science)
**Reason**: Documents the multi-agent architecture and workflow for algo trading research. Contains specific agent assignments, schedules, and project structure.

**Git Value**: High - unique project architecture that would be valuable to preserve and share with team members.

#### ✅ `moon-control` (smart-home)
**Reason**: Reverse-engineered control protocol for MOON 390 (MiND 2) network audio player. Contains full NetAPI XML protocol (48 methods), airable cloud API integration for Deezer/Tidal content browsing, and SSDP device discovery. Built from APK decompilation of the official MiND app.

**Git Value**: High — unique reverse-engineering result for a niche high-end audio device. Protocol knowledge would be lost without version control.

### System Configuration & Setup

#### ✅ `distrobox-vulkan-env-bug` (devops)
**Reason**: Documents specific workarounds for distrobox and AMDVLK Vulkan issues.

**Git Value**: Medium - environment-specific, but the debugging patterns are reusable.

#### ✅ `strix-halo-monitoring` (mlops)
**Reason**: Documents monitoring setup for Strix Halo APU hardware.

**Git Value**: Medium - hardware-specific monitoring knowledge.

### Memory & Persistence Systems

#### ✅ `obsidian-rag` (memory)
**Reason**: Documents the Obsidian-ChromaDB integration architecture and workflow.

**Git Value**: High - novel approach to memory persistence that could be valuable to others.

#### ✅ `rag-auto-lookup` (memory)
**Reason**: Documents the automatic RAG query system.

**Git Value**: Medium - specific implementation pattern, but the concept is reusable.

---

## Skills NOT Recommended for Git

### ❌ Temporary/Debug Skills
- `dogfood` - QA testing skills are temporary by nature
- `voicemail-handler` - very specific use case

### ❌ Platform-Specific Private Skills
- `yuanbao` - internal messaging platform tools
- Platform-specific authentication skills

### ❌ Creative/Content Skills
- Most `creative` category skills (ascii-art, architecture-diagram, etc.)
- These are utility tools, not persistent knowledge

### ❌ Generic Third-Party Integrations
- Skills that just wrap third-party APIs without added value
- Skills that could be replaced by official documentation

### ❌ Highly Personalized Skills
- Skills with hardcoded personal preferences or configurations
- Skills that depend on unique personal workflows

---

## Skills to Consider for Future Review

### 🔍 Under Evaluation
- `webhook-subscriptions` - might be valuable if webhook patterns are documented
- `skill-maintenance` - if it contains general skill maintenance patterns

---

## Maintenance Guidelines

1. **Regular Review**: Whitelist should be reviewed quarterly to ensure criteria are still appropriate
2. **Skill Updates**: When updating whitelisted skills, ensure they continue to meet criteria
3. **New Skills**: New skills should be evaluated against these criteria before being added to git
4. **Documentation**: Each whitelisted skill should have clear documentation of its git value

---

## Git Structure Recommendation

```
skills/
├── core/                 # Infrastructure and system skills
│   ├── router-troubleshooting/
│   ├── model-manager/
│   └── github-auth/
├── projects/             # Project-specific architectures
│   └── algotrading-agent-army-resume/
├── devops/              # DevOps and configuration
│   ├── openwebui-tool-management/
│   └── distrobox-vulkan-env-bug/
└── memory/              # Memory and persistence systems
    ├── obsidian-rag/
    └── rag-auto-lookup/
```

This structure groups skills by their domain and makes it easier to navigate the git repository.
