# The Guild MCP server

Lets a client's AI (Claude Desktop, Cursor, any MCP client) quote and hire the guild.
It only calls the guild's public API with an API key.

Tools:
- `quote_guild_job(brief)`: priced milestones and a `quote_id`
- `hire_guild(quote_id, client_name, client_email)`: makes the job, returns the client's `portal_url`
- `check_guild_job(job_id)`: worker, agreement, milestones, what happens next

## Setup on Windows
```
cd mcp
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```
Get a key: log in as an admin, open Activity, "Hire by agent", Make a key.

Open `%APPDATA%\Claude\claude_desktop_config.json` and add:
```json
{
  "mcpServers": {
    "guild": {
      "command": "E:/Education/Practical/Paypal/The-Guild/mcp/.venv/Scripts/python.exe",
      "args": ["E:/Education/Practical/Paypal/The-Guild/mcp/guild_mcp.py"],
      "env": {
        "GUILD_API_KEY": "guild_...",
        "GUILD_API_URL": "https://guild-backend-vqg5.onrender.com"
      }
    }
  }
}
```
Quit Claude Desktop fully (system tray too) and open it again.

Try: "Ask The Guild for a quote: a React landing page for my coffee subscription, budget $800, two weeks."
Then: "Looks good, hire them. I'm Anna Startup, client1-sb@personal.example.com."

`mcp` is pinned below 2.0 because 2.x renamed the server class.
