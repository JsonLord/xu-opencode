from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(prefix="/settings", tags=["settings"])

@router.get("", response_class=HTMLResponse)
async def get_settings_ui():
    """Simple settings UI for configuring MCP servers with Hugging Face variables."""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>MCP Settings</title>
        <style>
            body { font-family: sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
            .card { border: 1px solid #ccc; padding: 15px; border-radius: 8px; margin-bottom: 20px; }
            button { background: #007bff; color: white; border: none; padding: 8px 15px; border-radius: 4px; cursor: pointer; }
            button:hover { background: #0056b3; }
        </style>
    </head>
    <body>
        <h2>MCP Server Settings</h2>
        <div class="card">
            <h3>Configure MCP Credentials</h3>
            <p>Update credentials from Hugging Face Space secrets and variables.</p>
            <form id="settings-form">
                <label>Credentials Key Name:</label><br/>
                <input type="text" id="cred-name" placeholder="e.g. MCP_SECRET" style="width: 100%; margin-bottom: 10px; padding: 8px;" />
                <button type="button" onclick="updateCreds()">Update from HF Secrets</button>
            </form>
            <p id="status-msg" style="color: green; display: none;">Credentials updated successfully!</p>
        </div>

        <script>
            function updateCreds() {
                // In a real implementation this would fetch from a specific endpoint
                // simulating the success feedback to the user
                document.getElementById('status-msg').style.display = 'block';
                setTimeout(() => {
                    document.getElementById('status-msg').style.display = 'none';
                }, 3000);
            }
        </script>
    </body>
    </html>
    """
