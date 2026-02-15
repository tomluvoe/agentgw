# Sub-Agent Orchestration - Implementation Summary (v1.5)

## Overview

Implemented complete sub-agent orchestration system allowing skills to delegate tasks to other specialized skills, enabling complex multi-step workflows with depth tracking and recursion prevention.

## Features Implemented

### 1. `delegate_to_agent` Meta-Tool

**Location:** `src/agentgw/tools/delegation_tools.py`

**Function signature:**
```python
async def delegate_to_agent(
    skill_name: str,
    task: str,
    context: str | None = None,
) -> dict
```

**Returns:**
```python
{
    "status": "ok",
    "skill": "skill_name",
    "result": "agent response",
    "depth": 1
}
# Or on error:
{
    "error": "error message",
    "current_depth": N  # optional
}
```

**Features:**
- Delegates task execution to another skill
- Optionally provides additional context
- Tracks orchestration depth automatically
- Enforces max depth limits
- Creates isolated session for delegated task
- Returns structured results

### 2. Orchestration Depth Tracking

**Location:** `src/agentgw/core/agent.py`

**Implementation:**
- Uses Python `ContextVar` for async-safe depth tracking
- `get_current_orchestration_depth()` - Returns current depth
- `set_current_orchestration_depth(depth)` - Sets depth
- Depth preserved across async calls
- Auto-incremented during delegation
- Auto-decremented after delegation completes

**Workflow:**
```
Orchestrator (depth=0)
    └─> Delegate to Skill A
            Skill A (depth=1)
                └─> Delegate to Skill B
                        Skill B (depth=2)
                            └─> Returns result
                    Skill A (depth=1) - depth restored
                └─> Returns result
        Orchestrator (depth=0) - depth restored
```

### 3. AgentLoop Enhancements

**Added constructor parameter:**
```python
def __init__(
    self,
    ...
    orchestration_depth: int = 0,  # NEW
):
```

**Behavior:**
- Sets depth in context variable when `run()` starts
- Passes depth to all tool executions
- Enables tools to check current depth

### 4. AgentService Integration

**Modified `create_agent()` method:**
```python
async def create_agent(
    self,
    skill_name: str,
    session_id: str | None = None,
    model_override: str | None = None,
    orchestration_depth: int | None = None,  # NEW - auto-detected if None
) -> tuple[AgentLoop, Session, Skill]:
```

**Features:**
- Auto-detects orchestration depth from context if not provided
- Passes depth to AgentLoop constructor
- Enables delegation tool to create sub-agents with correct depth

**Service wiring:**
```python
# In __init__
set_agent_service(self)  # Makes service available to delegation tool
```

### 5. Configuration

**Max depth setting in `config/settings.yaml`:**
```yaml
agent:
  max_orchestration_depth: 3  # Default
```

**Configurable via:**
- YAML config file
- Environment variable: `AGENTGW_AGENT__MAX_ORCHESTRATION_DEPTH=5`
- Prevents infinite recursion
- Reasonable default (3) for most use cases

### 6. Example Skills

**Project Manager Orchestrator:**
- File: `skills/project_manager.yaml`
- Coordinates complex multi-step projects
- Delegates to general_assistant and summarize_document
- Demonstrates delegation patterns
- Low temperature (0.3) for consistent orchestration

## Code Changes

### New Files

1. **`src/agentgw/tools/delegation_tools.py`**
   - `delegate_to_agent()` tool implementation
   - `set_agent_service()` initialization function
   - Error handling for max depth and missing skills

2. **`skills/project_manager.yaml`**
   - Example orchestrator skill
   - Demonstrates delegation patterns
   - Lists `sub_agents` for clarity

3. **`tests/test_delegation.py`**
   - 12 comprehensive tests
   - Depth tracking tests
   - Delegation tool tests
   - Orchestration workflow tests
   - Depth limits tests

4. **`examples/sub_agent_orchestration.md`**
   - Complete usage guide
   - Multiple examples
   - Best practices
   - Troubleshooting

### Modified Files

1. **`src/agentgw/core/agent.py`**
   - Added `ContextVar` for depth tracking
   - Added helper functions for depth get/set
   - Added `orchestration_depth` parameter to `__init__`
   - Sets depth in context variable during `run()`

2. **`src/agentgw/core/service.py`**
   - Imported `get_current_orchestration_depth`
   - Added `orchestration_depth` parameter to `create_agent()`
   - Auto-detection of depth from context
   - Wired up delegation tool with `set_agent_service()`

3. **`config/settings.yaml`**
   - Already had `max_orchestration_depth: 3`

4. **`README.md`**
   - Added sub-agent orchestration section
   - Updated roadmap (v1.5 complete)
   - Updated test count (73)
   - Added `delegate_to_agent` to built-in tools table
   - Added `project_manager.yaml` to project structure

5. **`CHANGELOG.md`**
   - Added v1.5 features to unreleased section
   - Updated test count
   - Marked v1.5 as complete in roadmap

## Architecture

### Delegation Flow

```
1. Orchestrator skill calls delegate_to_agent()
   ↓
2. Delegation tool checks current depth vs max depth
   ↓
3. If depth OK, increments depth (set_current_orchestration_depth(depth + 1))
   ↓
4. Creates new AgentLoop via AgentService.create_agent()
   ↓
5. Runs delegated task to completion (non-streaming)
   ↓
6. Restores depth (set_current_orchestration_depth(original_depth))
   ↓
7. Returns structured result to orchestrator
```

### Context Variable Benefits

- **Async-safe**: Works correctly with concurrent delegations
- **Automatic propagation**: Depth flows through async call chain
- **Isolated**: Each async context has its own depth value
- **No manual passing**: Tools automatically have access via context

### Session Isolation

Each delegation creates a **new session**:
- Delegated agent has clean conversation history
- No pollution from parent agent's context
- Results are isolated and returned as strings
- Parent must explicitly pass context via `context` parameter

## Testing

### Test Coverage (12 new tests)

**TestOrchestrationDepth (3 tests):**
- Default depth is zero
- Set and get depth
- AgentLoop sets depth from constructor

**TestDelegationTool (5 tests):**
- Delegation without service initialized
- Max depth reached
- Delegation to nonexistent skill
- Depth increments during delegation
- Delegation with context parameter

**TestOrchestrationWorkflow (2 tests):**
- Create agent with explicit orchestration depth
- Auto-detection of orchestration depth

**TestOrchestrationLimits (2 tests):**
- Default max depth is configured
- Delegation respects max depth

### Total Tests: 73 (61 original + 12 new)

All tests passing ✅

## Use Cases

### 1. Complex Research Projects

```yaml
name: research_coordinator
tools: [delegate_to_agent, search_documents]
sub_agents: [general_assistant, summarize_document]
```

Workflow:
1. Search for relevant documents
2. Delegate research to general_assistant
3. Delegate summarization to summarize_document
4. Synthesize findings

### 2. Code Generation & Review

```yaml
name: code_reviewer
tools: [delegate_to_agent, read_file]
sub_agents: [code_assistant]
```

Workflow:
1. Read source files
2. Delegate code generation to code_assistant
3. Delegate review to same or different skill
4. Compile comprehensive feedback

### 3. Multi-Step Analysis

```yaml
name: data_analyst
tools: [delegate_to_agent, query_db]
sub_agents: [general_assistant]
```

Workflow:
1. Query database for raw data
2. Delegate statistical analysis
3. Delegate visualization recommendations
4. Create executive summary

## Design Decisions

### Why ContextVar?

**Alternatives considered:**
- Thread-local storage (not async-safe)
- Manual depth parameter passing (too verbose)
- Global variable (not safe for concurrent executions)

**ContextVar wins:**
- Async-safe by design
- Automatic propagation
- Isolated per execution context
- Standard library solution

### Why Non-Streaming Delegation?

Delegated tasks use `run_to_completion()` instead of streaming:

**Reasons:**
- Simpler integration (orchestrator receives complete result)
- Easier error handling
- Results can be post-processed before use
- Streaming adds complexity without much benefit for delegation

**Trade-off:** User doesn't see delegated task progress in real-time.

### Why Session Isolation?

Each delegation creates a new session:

**Benefits:**
- Clean separation of concerns
- No context pollution
- Predictable behavior
- Easy to reason about

**Trade-off:** Parent context must be explicitly passed.

### Why Default Max Depth = 3?

**Reasoning:**
- Depth 0: Orchestrator
- Depth 1: Primary specialists
- Depth 2: Sub-specialists
- Depth 3: Rarely needed

Most real workflows need 1-2 levels. Depth of 3 provides buffer while preventing runaway recursion.

## Limitations & Considerations

### 1. Performance Overhead

Each delegation:
- Creates new session
- Initializes new AgentLoop
- Runs full ReAct loop
- Serializes results

**Implication:** Use for genuinely complex subtasks, not trivial operations.

### 2. Context Loss

Delegated agents don't have access to:
- Parent conversation history
- Parent tool execution results
- Parent session state

**Mitigation:** Pass critical context via `context` parameter.

### 3. Depth Limit

Default depth of 3 may limit some advanced workflows.

**Mitigation:** Increase `max_orchestration_depth` in config if needed.

### 4. Error Propagation

Errors from delegated agents return as dict structures, not exceptions.

**Mitigation:** Always check for `"error"` key in delegation results.

## Future Enhancements

Potential improvements:

- [ ] Streaming delegation (show sub-agent progress)
- [ ] Parallel delegation (run multiple delegations concurrently)
- [ ] Delegation with shared context (optional context inheritance)
- [ ] Delegation history tracking (see full delegation chain)
- [ ] Delegation visualization in Web UI
- [ ] Cost tracking per delegation level
- [ ] Timeout controls for delegations

## Backward Compatibility

✅ **100% backward compatible:**
- No changes to existing skills
- No changes to existing tool calls
- No changes to existing APIs
- `orchestration_depth` parameter is optional (defaults to 0)
- Purely additive functionality

## Documentation

**Created:**
- `examples/sub_agent_orchestration.md` - Complete usage guide
- `SUB_AGENT_ORCHESTRATION.md` - This technical summary

**Updated:**
- `README.md` - Added orchestration section
- `CHANGELOG.md` - Added v1.5 features
- `skills/_schema.yaml` - Already documented `sub_agents` field

## Summary

v1.5 sub-agent orchestration is **complete** with:
- ✅ Full delegation tool implementation
- ✅ Depth tracking with ContextVar
- ✅ Max depth enforcement
- ✅ Service integration
- ✅ Example orchestrator skill
- ✅ Comprehensive testing (12 new tests)
- ✅ Complete documentation
- ✅ Backward compatible

The system enables complex multi-step workflows while preventing infinite recursion and maintaining clean separation of concerns.
