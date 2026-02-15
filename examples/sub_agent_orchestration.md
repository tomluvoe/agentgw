# Sub-Agent Orchestration Guide

This guide demonstrates how to use the `delegate_to_agent` tool to coordinate complex tasks across multiple specialized agents.

## Overview

Sub-agent orchestration allows one skill to delegate tasks to other specialized skills, enabling:
- **Complex workflows**: Break down large tasks into manageable subtasks
- **Specialization**: Leverage domain-specific skills for each subtask
- **Coordination**: Combine results from multiple agents
- **Depth limiting**: Prevent infinite recursion with configurable max depth

## The `delegate_to_agent` Tool

```python
delegate_to_agent(
    skill_name: str,      # Name of the skill to delegate to
    task: str,            # The specific task or question
    context: str | None   # Optional additional context
) -> dict               # Returns {"status": "ok", "result": "...", "skill": "...", "depth": N}
```

## Basic Example

### Simple Delegation

```yaml
name: research_coordinator
description: Coordinates research tasks
system_prompt: |
  You coordinate research by delegating to specialized agents.

tools:
  - delegate_to_agent

sub_agents:
  - general_assistant
```

**Usage:**
```bash
agentgw chat --skill research_coordinator
> Research Python async programming and summarize the key concepts

# The coordinator will:
# 1. Delegate research to general_assistant
# 2. Delegate summarization to summarize_document
# 3. Combine results
```

## Advanced Example: Project Manager

The `project_manager` skill demonstrates complex orchestration:

```yaml
name: project_manager
description: Orchestrates multi-step projects by delegating to specialized agents
system_prompt: |
  You are a project manager that coordinates complex tasks.

  Break down tasks into subtasks and delegate to:
  - general_assistant: Research, explanations, general tasks
  - summarize_document: Document analysis and summarization

  Always explain your delegation strategy before executing.

tools:
  - delegate_to_agent

sub_agents:
  - general_assistant
  - summarize_document
```

### Example Workflow

**User request:**
> "Create a comprehensive guide on FastAPI with code examples and best practices"

**Agent workflow:**
1. **Plan**: Break into subtasks
   - Explain FastAPI basics
   - Provide code examples
   - List best practices

2. **Delegate** each subtask:
   ```python
   # Task 1: Basics
   result1 = delegate_to_agent(
       "general_assistant",
       "Explain FastAPI fundamentals and core concepts"
   )

   # Task 2: Examples
   result2 = delegate_to_agent(
       "general_assistant",
       "Provide 3 practical FastAPI code examples",
       context="Focus on REST API patterns"
   )

   # Task 3: Best practices
   result3 = delegate_to_agent(
       "general_assistant",
       "List FastAPI best practices for production"
   )
   ```

3. **Synthesize**: Combine results into a comprehensive guide

## Orchestration Depth

### Depth Tracking

Each delegation increments the orchestration depth:

```
project_manager (depth=0)
    └─> delegates to general_assistant (depth=1)
            └─> could delegate further (depth=2)
                    └─> etc.
```

### Configuring Max Depth

In `config/settings.yaml`:

```yaml
agent:
  max_orchestration_depth: 3  # Default, prevents infinite recursion
```

### Depth Limits

When max depth is reached, delegation returns an error:

```python
{
    "error": "Maximum orchestration depth (3) reached. Cannot delegate further.",
    "current_depth": 3
}
```

## Use Cases

### 1. Research & Analysis

```yaml
name: research_analyst
tools: [delegate_to_agent]
sub_agents: [general_assistant, summarize_document]
```

Workflow:
1. Delegate broad research to `general_assistant`
2. Delegate document summarization to `summarize_document`
3. Combine findings

### 2. Code Review Coordinator

```yaml
name: code_reviewer
tools: [delegate_to_agent, read_file]
sub_agents: [code_assistant, general_assistant]
```

Workflow:
1. Read code files
2. Delegate security review to one agent
3. Delegate style review to another
4. Compile comprehensive review

### 3. Multi-Source Information Gathering

```yaml
name: info_aggregator
tools: [delegate_to_agent, search_documents]
sub_agents: [general_assistant]
```

Workflow:
1. Search multiple knowledge bases
2. Delegate analysis of each source
3. Aggregate and deduplicate findings

## Best Practices

### 1. Clear Task Decomposition

```python
# Good: Specific, focused tasks
delegate_to_agent("code_assistant", "Write a function to validate emails")

# Less effective: Vague, multi-part tasks
delegate_to_agent("code_assistant", "Do some coding stuff")
```

### 2. Provide Context

```python
delegate_to_agent(
    "general_assistant",
    "Explain REST API authentication",
    context="Focus on JWT tokens and OAuth 2.0 for a beginner audience"
)
```

### 3. Handle Delegation Errors

```python
result = delegate_to_agent("skill_name", "task")

if "error" in result:
    # Handle max depth, unknown skill, etc.
    return f"Delegation failed: {result['error']}"
else:
    # Process successful result
    return result["result"]
```

### 4. Avoid Deep Recursion

```yaml
# Configure reasonable max depth
agent:
  max_orchestration_depth: 3  # Usually sufficient
```

Most workflows need only 1-2 levels:
- Level 0: Orchestrator
- Level 1: Specialized agents
- Level 2: (rarely needed) Sub-specialized agents

### 5. Document Sub-Agent Relationships

```yaml
sub_agents:
  - general_assistant  # For research and explanations
  - code_assistant     # For code generation and review
  - summarize_document # For document analysis
```

## Limitations & Considerations

### 1. Context Isolation

Each delegated agent has its own session and context. They don't share:
- Conversation history
- Session state
- Previous tool executions

**Implication**: Pass necessary context explicitly via the `context` parameter.

### 2. Performance

Delegation incurs overhead:
- New session creation
- Full agent loop execution
- Result serialization

**Implication**: Use delegation for genuinely complex tasks, not trivial operations.

### 3. Error Propagation

Errors from delegated agents return as dicts:

```python
{
    "error": "Skill 'unknown_skill' not found"
}
```

**Implication**: Always check for errors in delegation results.

### 4. Depth Limit

Default max depth prevents infinite loops but may limit some workflows.

**Implication**: Design workflows with 2-3 levels max, or increase limit in config.

## Debugging

### Viewing Orchestration Depth

In logs, orchestration depth is tracked:

```
INFO: Agent iteration 1/15 (depth=0)
INFO: Delegating to general_assistant (depth=1)
INFO: Agent iteration 1/10 (depth=1)
```

### Testing Delegation

```bash
# Test orchestrator skill
agentgw chat --skill project_manager
> Test delegation by asking me to research something

# Check depth limits
agentgw chat --skill project_manager
> Trigger multiple levels of delegation
```

## Example: Multi-Step Research Project

```yaml
name: research_project
system_prompt: |
  You coordinate research projects with multiple phases:
  1. Information gathering
  2. Analysis
  3. Synthesis

  Delegate each phase to appropriate specialists.

tools: [delegate_to_agent, search_documents]
sub_agents: [general_assistant, summarize_document]
```

**User:** "Research machine learning deployment strategies"

**Agent execution:**
```python
# Phase 1: Gather information
ml_basics = delegate_to_agent(
    "general_assistant",
    "Explain machine learning model deployment basics"
)

# Phase 2: Analyze strategies
strategies = delegate_to_agent(
    "general_assistant",
    "Compare Docker vs Kubernetes for ML deployment",
    context=ml_basics["result"]
)

# Phase 3: Synthesize
summary = delegate_to_agent(
    "summarize_document",
    "Summarize the key findings about ML deployment",
    context=f"{ml_basics['result']}\n\n{strategies['result']}"
)

# Return comprehensive report
return f"""
# ML Deployment Research

## Basics
{ml_basics['result']}

## Strategy Comparison
{strategies['result']}

## Summary
{summary['result']}
"""
```

## Next Steps

1. **Create your orchestrator skill**: Copy `project_manager.yaml` as a template
2. **Define sub-agents**: List the skills you'll delegate to
3. **Write coordination logic**: Break tasks into subtasks
4. **Test delegation**: Verify depth limits and error handling
5. **Monitor performance**: Check if orchestration overhead is acceptable

For more examples, see the `project_manager` skill in `skills/project_manager.yaml`.
