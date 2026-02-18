from typing import Dict, Any, List
from .tool import BaseTool, ToolContext, ToolResult


class WebSearchTool(BaseTool):
    
    @property
    def id(self) -> str:
        return "websearch"
    
    @property
    def description(self) -> str:
        return (
            "Search the web using DuckDuckGo. Returns relevant search results "
            "with titles, URLs, and snippets. Use this when you need current "
            "information from the internet."
        )
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query"
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return (default: 5)",
                    "default": 5
                }
            },
            "required": ["query"]
        }
    
    async def execute(self, args: Dict[str, Any], ctx: ToolContext) -> ToolResult:
        query = args["query"]
        max_results = args.get("max_results", 5)
        
        try:
            from ddgs import DDGS

            results = []
            with DDGS() as ddgs:
                # 한국 지역 기반 검색 결과
                for r in ddgs.text(query, region="kr-kr", max_results=max_results):
                    results.append({
                        "title": r.get("title", ""),
                        "url": r.get("href", ""),
                        "snippet": r.get("body", "")
                    })
            
            if not results:
                return ToolResult(
                    title=f"Web search: {query}",
                    output="No results found.",
                    metadata={"query": query, "count": 0}
                )
            
            output_lines = []
            for i, r in enumerate(results, 1):
                output_lines.append(f"{i}. {r['title']}")
                output_lines.append(f"   URL: {r['url']}")
                output_lines.append(f"   {r['snippet']}")
                output_lines.append("")
            
            return ToolResult(
                title=f"Web search: {query}",
                output="\n".join(output_lines),
                metadata={"query": query, "count": len(results)}
            )
            
        except ImportError:
            return ToolResult(
                title=f"Web search: {query}",
                output="Error: ddgs package not installed. Run: pip install ddgs",
                metadata={"error": "missing_dependency"}
            )
        except Exception as e:
            return ToolResult(
                title=f"Web search: {query}",
                output=f"Error performing search: {str(e)}",
                metadata={"error": str(e)}
            )
