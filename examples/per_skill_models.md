# Per-Skill Model Selection Guide

This guide demonstrates how to configure different LLM models for different skills based on their complexity and requirements.

## Overview

Each skill can specify its own model in the YAML configuration. This allows you to:
- **Optimize costs**: Use smaller models for simple tasks
- **Maximize capability**: Use powerful models for complex reasoning
- **Balance performance**: Match model capabilities to task requirements

## Configuration

### In Skill YAML

```yaml
name: my_skill
description: Description here
system_prompt: |
  System prompt here

model: gpt-4o  # Specify the model for this skill
temperature: 0.7
```

### Model Selection Hierarchy

1. **Command-line override** (`agentgw chat --model`)
2. **Skill-specific model** (in YAML)
3. **Global default** (in `config/settings.yaml`)

## Common Model Choices

### GPT-4o (Most Capable)

**Best for:**
- Complex reasoning tasks
- Code generation and review
- Multi-step problem solving
- Advanced analysis

**Example:**
```yaml
name: code_assistant
model: gpt-4o
temperature: 0.3  # Lower for deterministic code
```

### GPT-4o-mini (Balanced)

**Best for:**
- General purpose tasks
- Document summarization
- Question answering
- Content generation

**Example:**
```yaml
name: general_assistant
# model: gpt-4o-mini  # Or omit to use global default
temperature: 0.7
```

### Custom Models

```yaml
name: specialized_skill
model: gpt-4o-2024-08-06  # Specific version
temperature: 0.5
```

## Example Configurations

### 1. Code Assistant (Complex Reasoning)

```yaml
name: code_assistant
description: Expert programming assistant
system_prompt: |
  You are an expert programmer...

tools:
  - read_file
  - list_files

model: gpt-4o  # Most capable model for code
temperature: 0.3  # Deterministic output
```

**Why gpt-4o:**
- Better code quality
- Handles complex algorithms
- More accurate debugging
- Worth the cost for code tasks

### 2. Quick Assistant (Simple Tasks)

```yaml
name: quick_assistant
description: Fast responses for simple queries
system_prompt: |
  You provide quick, concise answers...

tools:
  - search_documents

model: gpt-4o-mini  # Fast and cost-effective
temperature: 0.7
```

**Why gpt-4o-mini:**
- Faster responses
- Lower cost
- Sufficient for simple tasks
- Good for high-volume use

### 3. Document Summarizer (Moderate Complexity)

```yaml
name: summarize_document
description: Summarizes documents
system_prompt: |
  You create concise summaries...

tools:
  - read_file

# No model specified = uses global default
temperature: 0.5  # Balanced creativity/consistency
```

**Why default:**
- Flexible - can change globally
- Good for standard tasks
- Easy to upgrade all at once

### 4. Research Coordinator (Orchestration)

```yaml
name: research_coordinator
description: Coordinates research tasks
system_prompt: |
  You coordinate complex research...

tools:
  - delegate_to_agent
  - search_documents

model: gpt-4o  # Needs good reasoning for orchestration
temperature: 0.3  # Consistent delegation logic
```

**Why gpt-4o:**
- Better task decomposition
- More reliable delegation
- Improved result synthesis

## Cost Optimization Strategies

### Strategy 1: Tiered Approach

```
User Request
    ↓
Quick Assistant (gpt-4o-mini) - First attempt
    ↓ (if complex)
General Assistant (default)
    ↓ (if very complex)
Code Assistant (gpt-4o) - Last resort
```

### Strategy 2: Task-Specific Models

```
Simple Queries     → quick_assistant (gpt-4o-mini)
General Tasks      → general_assistant (default)
Code Generation    → code_assistant (gpt-4o)
Document Analysis  → summarize_document (default)
Orchestration      → project_manager (gpt-4o)
```

### Strategy 3: Volume-Based

```
High-Volume Skills  → gpt-4o-mini
    - customer_support
    - quick_faq
    - simple_tasks

Low-Volume Skills → gpt-4o
    - complex_analysis
    - code_review
    - research_deep
```

## Testing Different Models

### Via CLI Override

```bash
# Test with different models
agentgw chat --skill code_assistant --model gpt-4o
agentgw chat --skill code_assistant --model gpt-4o-mini

# Compare results
```

### Via Skill Modification

```bash
# Edit skill file
vim skills/my_skill.yaml

# Change model field
model: gpt-4o-mini  # from gpt-4o

# Test
agentgw chat --skill my_skill
```

## Model Selection Guidelines

### Use GPT-4o When:
- ✅ Task requires deep reasoning
- ✅ Code quality is critical
- ✅ Complex multi-step processes
- ✅ Accuracy > speed/cost

### Use GPT-4o-mini When:
- ✅ Simple question answering
- ✅ High-volume operations
- ✅ Speed is important
- ✅ Cost optimization needed

### Use Default (No Specification) When:
- ✅ Task complexity varies
- ✅ Want flexibility to change globally
- ✅ Standard capabilities sufficient

## Real-World Examples

### Example 1: Customer Support System

```yaml
# Triage skill - high volume, simple
name: support_triage
model: gpt-4o-mini
temperature: 0.7

# Technical support - complex issues
name: technical_support
model: gpt-4o
temperature: 0.5
```

### Example 2: Content Creation Pipeline

```yaml
# Outline generation - quick brainstorming
name: content_outliner
model: gpt-4o-mini
temperature: 0.9

# Final writing - quality matters
name: content_writer
model: gpt-4o
temperature: 0.7

# Editing - needs precision
name: content_editor
model: gpt-4o
temperature: 0.3
```

### Example 3: Development Workflow

```yaml
# Code generation
name: code_generator
model: gpt-4o
temperature: 0.3

# Code review
name: code_reviewer
model: gpt-4o
temperature: 0.2

# Documentation
name: doc_writer
model: gpt-4o-mini  # Sufficient for docs
temperature: 0.7
```

## Monitoring and Optimization

### Track Usage

```bash
# Check which skills are used most
agentgw sessions --skill code_assistant | wc -l
agentgw sessions --skill quick_assistant | wc -l
```

### Analyze Costs

```
High-Cost Skills (consider optimization):
- code_assistant (gpt-4o) - 500 calls/day
- research_coordinator (gpt-4o) - 200 calls/day

Low-Impact Skills (can use better model):
- quick_assistant (gpt-4o-mini) - 1000 calls/day
```

### Optimize Iteratively

1. Start with default models
2. Identify high-cost skills
3. Test with cheaper models
4. Measure quality impact
5. Adjust accordingly

## Common Patterns

### Pattern 1: Planner + Specialists

```yaml
# Planner uses powerful model
name: task_planner
model: gpt-4o
tools: [delegate_to_agent]

# Specialists use appropriate models
name: data_processor
model: gpt-4o-mini  # Simple transformations

name: insight_generator
model: gpt-4o  # Complex analysis
```

### Pattern 2: Progressive Enhancement

```yaml
# Level 1: Fast first response
name: quick_responder
model: gpt-4o-mini

# Level 2: Detailed follow-up
name: detailed_assistant
model: gpt-4o
```

### Pattern 3: Domain-Specific

```yaml
# Math/logic - needs precision
name: math_tutor
model: gpt-4o
temperature: 0.1

# Creative writing - needs variety
name: creative_writer
model: gpt-4o
temperature: 0.9

# Data entry - simple tasks
name: data_entry
model: gpt-4o-mini
temperature: 0.3
```

## Troubleshooting

### Model Not Found

```
Error: Model 'gpt-5' not available
```

**Solution**: Check OpenAI's model list, use valid model name.

### Unexpected Costs

**Check:**
1. Which skills use which models?
2. Call frequency per skill?
3. Are expensive models necessary?

### Quality Issues

**Try:**
1. Increase model capability (mini → 4o)
2. Adjust temperature
3. Improve system prompt
4. Add few-shot examples

## Best Practices

1. **Start Conservative**: Use defaults, upgrade as needed
2. **Measure Impact**: Track quality vs. cost
3. **Document Decisions**: Note why each skill uses its model
4. **Review Periodically**: Re-evaluate as models improve
5. **Test Changes**: Compare outputs before deploying

## Summary

Per-skill model selection enables you to:
- Match model capability to task complexity
- Optimize costs without sacrificing quality
- Maintain flexibility as requirements change
- Scale efficiently as usage grows

Choose models based on:
- Task complexity
- Volume of use
- Quality requirements
- Cost constraints
- Response time needs
