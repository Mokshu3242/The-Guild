param([string]$BaseUrl = "http://127.0.0.1:8000")

$script:pass = 0
$script:fail = 0

function Call($Method, $Path, $Token = $null, $Body = $null) {
    $headers = @{}
    if ($Token) { $headers["Authorization"] = "Bearer $Token" }
    $params = @{
        Method     = $Method
        Uri        = "$BaseUrl$Path"
        Headers    = $headers
        TimeoutSec = 90
    }
    if ($Body) {
        $params.Body = ($Body | ConvertTo-Json -Depth 5)
        $params.ContentType = "application/json"
    }
    try {
        $data = Invoke-RestMethod @params
        return @{ Status = 200; Data = $data }
    } catch {
        $code = 0
        if ($_.Exception.Response) { $code = [int]$_.Exception.Response.StatusCode }
        return @{ Status = $code; Data = $_.ErrorDetails.Message }
    }
}

function Check($Name, $Result, $Expected) {
    if ($Result.Status -eq $Expected) {
        Write-Host "PASS  $Name ($($Result.Status))" -ForegroundColor Green
        $script:pass++
    } else {
        Write-Host "FAIL  $Name (got $($Result.Status), expected $Expected)" -ForegroundColor Red
        Write-Host "      $($Result.Data)" -ForegroundColor DarkGray
        $script:fail++
    }
}

function Get-Token($Email, $Password) {
    return (python -m scripts.get_token $Email $Password | Select-Object -Last 1).Trim()
}

Write-Host "`nTesting $BaseUrl`n" -ForegroundColor Cyan

# --- Public routes ---
Check "Health check" (Call GET "/health") 200
Check "Root info"    (Call GET "/")       200

# --- Auth protection ---
Check "No token is rejected"  (Call GET "/me")                    401
Check "Bad token is rejected" (Call GET "/me" "not-a-real-token") 401

# --- Get tokens ---
Write-Host "`nGetting tokens..." -ForegroundColor Cyan
$maya = Get-Token "maya@guild.test" "maya@123"
$leo  = Get-Token "leo@guild.test"  "leo@123"
$sara = Get-Token "sara@guild.test" "sara@123"

# --- Maya (admin) ---
Write-Host "`nMaya (admin)" -ForegroundColor Cyan
$me = Call GET "/me" $maya
Check "Maya GET /me" $me 200
$guildId = $me.Data.guild_id
Write-Host "      Guild ID: $guildId" -ForegroundColor DarkGray

Check "Maya sees her guild"     (Call GET  "/guilds/$guildId"         $maya) 200
Check "Maya lists members"      (Call GET  "/guilds/$guildId/members" $maya) 200
Check "Maya can rotate invite"  (Call POST "/guilds/$guildId/invite"  $maya) 200
Check "Maya sees earnings"      (Call GET  "/me/earnings"             $maya) 200

# --- Leo (member) ---
Write-Host "`nLeo (member)" -ForegroundColor Cyan
Check "Leo GET /me"             (Call GET "/me"   $leo) 200
Check "Leo lists jobs"          (Call GET "/jobs" $leo) 200

$newJob = Call POST "/jobs" $leo @{
    client_name  = "Smoke Test Client"
    client_email = "client1-sb@personal.example.com"
    description  = "Smoke test job created by the test script."
}
Check "Leo posts a job" $newJob 200
if ($newJob.Data.id) {
    Check "Leo reads that job" (Call GET "/jobs/$($newJob.Data.id)" $leo) 200
}

# --- Rules that must block ---
Write-Host "`nSafety rules" -ForegroundColor Cyan
Check "Leo can't join twice" (Call POST "/guilds/join" $leo @{
    invite_code = "anything"; name = "Leo"
}) 400
Check "Leo can't rotate invite (not admin)" (Call POST "/guilds/$guildId/invite" $leo) 403
Check "Leo can't see another guild" (Call GET "/guilds/00000000-0000-0000-0000-000000000000" $leo) 403
Check "Short job description is rejected" (Call POST "/jobs" $leo @{
    client_name = "X"; client_email = "x@x.com"; description = "short"
}) 422

# --- Sara ---
Write-Host "`nSara" -ForegroundColor Cyan
$saraMe = Call GET "/me" $sara
if ($saraMe.Status -eq 404) {
    Write-Host "SKIP  Sara hasn't joined the guild yet" -ForegroundColor Yellow
} else {
    Check "Sara GET /me" $saraMe 200
}

# --- Summary ---
Write-Host "`n$script:pass passed, $script:fail failed`n" -ForegroundColor Cyan