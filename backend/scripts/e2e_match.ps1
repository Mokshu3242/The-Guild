param([string]$BaseUrl = "http://127.0.0.1:8000")

function Call($Method, $Path, $Token, $Body = $null) {
    $params = @{
        Method = $Method; Uri = "$BaseUrl$Path"; TimeoutSec = 120
        Headers = @{ Authorization = "Bearer $Token" }
    }
    if ($Body) { $params.Body = ($Body | ConvertTo-Json -Depth 5); $params.ContentType = "application/json" }
    try { return Invoke-RestMethod @params }
    catch { Write-Host "FAILED $Method $Path" -ForegroundColor Red; Write-Host $_.ErrorDetails.Message; exit 1 }
}
function Get-Token($Email, $Password) {
    return (python -m scripts.get_token $Email $Password | Select-Object -Last 1).Trim()
}
function Step($Text) { Write-Host "`n>> $Text" -ForegroundColor Cyan }

$maya = Get-Token "maya@guild.test" "maya@123"
$leo  = Get-Token "leo@guild.test"  "leo@123"

Step "Make sure Leo is available"
Call PATCH "/me" $leo @{ available = $true } | Out-Null

Step "Maya posts a React job"
$job = Call POST "/jobs" $maya @{
    client_name  = "Anna Startup"
    client_email = "client1-sb@personal.example.com"
    description  = "Build a React and Tailwind landing page from a finished Figma design. Mobile first, four sections, two weeks."
}
Write-Host "   Job: $($job.id)"

Step "AI suggests a match (no assign yet)"
(Call POST "/jobs/$($job.id)/match" $maya @{ auto_assign = $false }) | ConvertTo-Json

Step "AI matches and assigns"
$pick = Call POST "/jobs/$($job.id)/match" $maya @{ auto_assign = $true }
$pick | ConvertTo-Json
Write-Host "   Expected: Leo (React + Tailwind)" -ForegroundColor DarkGray

Step "Job after assign"
$after = Call GET "/jobs/$($job.id)" $maya
Write-Host "   Status: $($after.status)  Worker: $($after.worker_id)"
Write-Host "   Reason: $($after.match_reason)"

Step "Agent log"
(Call GET "/agent/actions?limit=3" $maya) | Select-Object action, created_at | Format-Table