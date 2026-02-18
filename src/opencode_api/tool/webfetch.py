from typing import Dict, Any
import httpx
from .tool import BaseTool, ToolContext, ToolResult


class WebFetchTool(BaseTool):
    
    @property
    def id(self) -> str:
        return "webfetch"
    
    @property
    def description(self) -> str:
        return (
            "Fetch content from a URL and convert it to readable text or markdown. "
            "Use this when you need to read the content of a specific web page."
        )
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to fetch"
                },
                "format": {
                    "type": "string",
                    "enum": ["text", "markdown", "html"],
                    "description": "Output format (default: markdown)",
                    "default": "markdown"
                }
            },
            "required": ["url"]
        }
    
    async def execute(self, args: Dict[str, Any], ctx: ToolContext) -> ToolResult:
        url = args["url"]
        output_format = args.get("format", "markdown")
        
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
                response = await client.get(
                    url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (compatible; OpenCode-API/1.0)"
                    }
                )
                response.raise_for_status()
                html_content = response.text
            
            if output_format == "html":
                content = html_content[:50000]  # Limit size
            elif output_format == "text":
                content = self._html_to_text(html_content)
            else:  # markdown
                content = self._html_to_markdown(html_content)
            
            if len(content) > 50000:
                content = content[:50000] + "\n\n[Content truncated...]"
            
            return ToolResult(
                title=f"Fetched: {url}",
                output=content,
                metadata={"url": url, "format": output_format, "length": len(content)}
            )
            
        except httpx.HTTPStatusError as e:
            return ToolResult(
                title=f"Fetch failed: {url}",
                output=f"HTTP Error {e.response.status_code}: {e.response.reason_phrase}",
                metadata={"error": "http_error", "status_code": e.response.status_code}
            )
        except httpx.RequestError as e:
            return ToolResult(
                title=f"Fetch failed: {url}",
                output=f"Request error: {str(e)}",
                metadata={"error": "request_error"}
            )
        except Exception as e:
            return ToolResult(
                title=f"Fetch failed: {url}",
                output=f"Error: {str(e)}",
                metadata={"error": str(e)}
            )
    
    def _html_to_text(self, html: str) -> str:
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            
            return soup.get_text(separator="\n", strip=True)
        except ImportError:
            import re
            text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text)
            return text.strip()
    
    def _html_to_markdown(self, html: str) -> str:
        try:
            import html2text
            h = html2text.HTML2Text()
            h.ignore_links = False
            h.ignore_images = True
            h.body_width = 0
            return h.handle(html)
        except ImportError:
            return self._html_to_text(html)
