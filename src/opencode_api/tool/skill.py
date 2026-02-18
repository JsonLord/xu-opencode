"""Skill tool - loads detailed instructions for specific tasks."""
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

from .tool import BaseTool, ToolResult, ToolContext


class SkillInfo(BaseModel):
    """Information about a skill."""
    name: str
    description: str
    content: str


# Built-in skills registry
_skills: Dict[str, SkillInfo] = {}


def register_skill(skill: SkillInfo) -> None:
    """Register a skill."""
    _skills[skill.name] = skill


def get_skill(name: str) -> Optional[SkillInfo]:
    """Get a skill by name."""
    return _skills.get(name)


def list_skills() -> List[SkillInfo]:
    """List all registered skills."""
    return list(_skills.values())


# Built-in default skills
DEFAULT_SKILLS = [
    SkillInfo(
        name="web-research",
        description="Comprehensive web research methodology for gathering information from multiple sources",
        content="""# Web Research Skill

## Purpose
Guide for conducting thorough web research to answer questions or gather information.

## Methodology

### 1. Query Formulation
- Break down complex questions into specific search queries
- Use different phrasings to get diverse results
- Include domain-specific terms when relevant

### 2. Source Evaluation
- Prioritize authoritative sources (official docs, reputable publications)
- Cross-reference information across multiple sources
- Note publication dates for time-sensitive information

### 3. Information Synthesis
- Compile findings from multiple sources
- Identify consensus vs. conflicting information
- Summarize key points clearly

### 4. Citation
- Always provide source URLs
- Note when information might be outdated

## Tools to Use
- `websearch`: For finding relevant pages
- `webfetch`: For extracting content from specific URLs

## Best Practices
- Start broad, then narrow down
- Use quotes for exact phrases
- Filter by date when freshness matters
- Verify claims with multiple sources
"""
    ),
    SkillInfo(
        name="code-explanation",
        description="Methodology for explaining code clearly to users of varying skill levels",
        content="""# Code Explanation Skill

## Purpose
Guide for explaining code in a clear, educational manner.

## Approach

### 1. Assess Context
- Determine user's apparent skill level
- Identify what aspect they're asking about
- Note any specific confusion points

### 2. Structure Explanation
- Start with high-level overview (what does it do?)
- Break down into logical sections
- Explain each component's purpose

### 3. Use Analogies
- Relate concepts to familiar ideas
- Use real-world metaphors when helpful
- Avoid overly technical jargon initially

### 4. Provide Examples
- Show simple examples first
- Build up to complex cases
- Include edge cases when relevant

### 5. Verify Understanding
- Use the question tool to check comprehension
- Offer to elaborate on specific parts
- Provide additional resources if needed

## Best Practices
- Don't assume prior knowledge
- Explain "why" not just "what"
- Use code comments effectively
- Highlight common pitfalls
"""
    ),
    SkillInfo(
        name="api-integration",
        description="Best practices for integrating with external APIs",
        content="""# API Integration Skill

## Purpose
Guide for properly integrating with external APIs.

## Key Considerations

### 1. Authentication
- Store API keys securely (environment variables)
- Never hardcode credentials
- Handle token refresh if applicable

### 2. Error Handling
- Implement retry logic for transient failures
- Handle rate limiting gracefully
- Log errors with context

### 3. Request Best Practices
- Set appropriate timeouts
- Use connection pooling
- Implement circuit breakers for resilience

### 4. Response Handling
- Validate response schemas
- Handle pagination properly
- Cache responses when appropriate

### 5. Testing
- Mock API responses in tests
- Test error scenarios
- Verify rate limit handling

## Common Patterns

```python
# Example: Robust API call
async def call_api(url, retries=3):
    for attempt in range(retries):
        try:
            response = await httpx.get(url, timeout=30)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                await asyncio.sleep(2 ** attempt)
            elif e.response.status_code >= 500:
                await asyncio.sleep(1)
            else:
                raise
    raise Exception("Max retries exceeded")
```
"""
    ),
    SkillInfo(
        name="debugging",
        description="Systematic approach to debugging problems",
        content="""# Debugging Skill

## Purpose
Systematic methodology for identifying and fixing bugs.

## Process

### 1. Reproduce the Issue
- Get exact steps to reproduce
- Note environment details
- Identify when it started happening

### 2. Gather Information
- Check error messages and stack traces
- Review recent changes
- Check logs for anomalies

### 3. Form Hypotheses
- List possible causes
- Rank by likelihood
- Consider recent changes first

### 4. Test Hypotheses
- Start with most likely cause
- Make minimal changes to test
- Verify each hypothesis before moving on

### 5. Implement Fix
- Fix root cause, not symptoms
- Add tests to prevent regression
- Document the fix

### 6. Verify Fix
- Confirm original issue is resolved
- Check for side effects
- Test related functionality

## Debugging Questions
- What changed recently?
- Does it happen consistently?
- What's different when it works?
- What are the exact inputs?

## Tools
- Use print/log statements strategically
- Leverage debuggers when available
- Check version differences
"""
    ),
    SkillInfo(
        name="task-planning",
        description="Breaking down complex tasks into manageable steps",
        content="""# Task Planning Skill

## Purpose
Guide for decomposing complex tasks into actionable steps.

## Methodology

### 1. Understand the Goal
- Clarify the end objective
- Identify success criteria
- Note any constraints

### 2. Identify Components
- Break into major phases
- List dependencies between parts
- Identify parallel vs. sequential work

### 3. Create Action Items
- Make each item specific and actionable
- Estimate effort/complexity
- Assign priorities

### 4. Sequence Work
- Order by dependencies
- Front-load risky items
- Plan for blockers

### 5. Track Progress
- Use todo tool to track items
- Update status as work progresses
- Re-plan when needed

## Best Practices
- Start with end goal in mind
- Keep items small (< 1 hour ideal)
- Include verification steps
- Plan for error cases

## Example Structure
1. Research & understand requirements
2. Design approach
3. Implement core functionality
4. Add error handling
5. Test thoroughly
6. Document changes
"""
    ),
]


def _get_skill_description(skills: List[SkillInfo]) -> str:
    """Generate description with available skills."""
    if not skills:
        return "Load a skill to get detailed instructions for a specific task. No skills are currently available."
    
    lines = [
        "Load a skill to get detailed instructions for a specific task.",
        "Skills provide specialized knowledge and step-by-step guidance.",
        "Use this when a task matches an available skill's description.",
        "",
        "<available_skills>",
    ]
    
    for skill in skills:
        lines.extend([
            f"  <skill>",
            f"    <name>{skill.name}</name>",
            f"    <description>{skill.description}</description>",
            f"  </skill>",
        ])
    
    lines.append("</available_skills>")
    
    return "\n".join(lines)


class SkillTool(BaseTool):
    """Tool for loading skill instructions."""
    
    def __init__(self, additional_skills: Optional[List[SkillInfo]] = None):
        """Initialize with optional additional skills."""
        # Register default skills
        for skill in DEFAULT_SKILLS:
            register_skill(skill)
        
        # Register additional skills if provided
        if additional_skills:
            for skill in additional_skills:
                register_skill(skill)
    
    @property
    def id(self) -> str:
        return "skill"
    
    @property
    def description(self) -> str:
        return _get_skill_description(list_skills())
    
    @property
    def parameters(self) -> Dict[str, Any]:
        skill_names = [s.name for s in list_skills()]
        examples = ", ".join(f"'{n}'" for n in skill_names[:3])
        hint = f" (e.g., {examples}, ...)" if examples else ""
        
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": f"The skill identifier from available_skills{hint}",
                    "enum": skill_names if skill_names else None
                }
            },
            "required": ["name"]
        }
    
    async def execute(self, args: Dict[str, Any], ctx: ToolContext) -> ToolResult:
        skill_name = args.get("name", "")
        
        skill = get_skill(skill_name)
        
        if not skill:
            available = ", ".join(s.name for s in list_skills())
            return ToolResult(
                title=f"Skill not found: {skill_name}",
                output=f'Skill "{skill_name}" not found. Available skills: {available or "none"}',
                metadata={"error": True}
            )
        
        output = f"""## Skill: {skill.name}

**Description**: {skill.description}

{skill.content}
"""
        
        return ToolResult(
            title=f"Loaded skill: {skill.name}",
            output=output,
            metadata={"name": skill.name}
        )
