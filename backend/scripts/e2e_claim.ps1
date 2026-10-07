param([string]$BaseUrl = "http://127.0.0.1:8000")

function Call($Method, $Path, $Token, $Body = $null, [switch]$AllowFail) {
    $params = @{
        Method = $Method; Uri = "$BaseUrl$Path"; TimeoutSec = 120
        Headers = @{ Authorization = "Bearer $Token" }
    }
    if ($Body) { $params.Body = ($Body | ConvertTo-Json -Depth 5); $params.ContentType = "application/json" }
    try { return Invoke-RestMethod @params }
    catch {
        if ($AllowFail) { return @{ error = $_.ErrorDetails.Message } }
        Write-Host "FAILED $Method $Path" -ForegroundColor Red; Write-Host $_.ErrorDetails.Message; exit 1
    }
}
function Get-Token($Email, $Password) {
    return (python -m scripts.get_token $Email $Password | Select-Object -Last 1).Trim()
}
function Step($Text) { Write-Host "`n>> $Text" -ForegroundColor Cyan }

$maya = Get-Token "maya@guild.test" "maya@123"
$leo  = Get-Token "leo@guild.test"  "leo@123"
$sara = Get-Token "sara@guild.test" "sara@123"

Step "Setup: Leo posts a job for Gary Ghost and assigns Sara"
$me = Call GET "/me" $leo
$members = Call GET "/guilds/$($me.guild_id)/members" $leo
$saraMember = $members | Where-Object { $_.name -eq "Sara" } | Select-Object -First 1

$job = Call POST "/jobs" $leo @{
    client_name  = "Gary Ghost"
    client_email = "client2-sb@personal.example.com"
    description  = "Write website copy for a fitness studio: home page, about page, and three class descriptions."
}
Call POST "/jobs/$($job.id)/assign" $leo @{ worker_id = $saraMember.id; match_reason = "Copywriter" } | Out-Null
$ms = Call POST "/jobs/$($job.id)/milestones" $leo @{
    title = "Website copy"; scope = "Home, about, and 3 class pages. 2 rounds of edits."; amount_cents = 6000
}
$inv = Call POST "/invoices/milestones/$($ms.id)/send" $leo
Write-Host "   Invoice: $($inv.id)  (do NOT pay this one)"

Step "Pool before"
$poolBefore = (Call GET "/pool" $sara).pool_balance_cents
Write-Host "   Pool: $poolBefore cents"

Step "Leo tries to claim (he's not the worker, should fail)"
(Call POST "/claims" $leo @{ invoice_id = $inv.id; statement = "Trying to claim a job I did not work on at all." } -AllowFail) | ConvertTo-Json

Step "Sara files a claim"
$res = Call POST "/claims" $sara @{
    invoice_id    = $inv.id
    statement     = "I delivered all five pages on time and the client confirmed by email they were happy. After that they stopped replying and never paid the invoice."
    evidence_urls = @("contract.pdf", "client_approval_email.png", "delivered_copy.docx")
}
$claim = $res.claim
Write-Host "   AI review: $($res.ai_review)"
Write-Host "   Verdict: $($claim.ai_verdict)  Confidence: $($claim.ai_confidence)"
Write-Host "   Reason: $($claim.ai_reason)"

Step "Sara tries to claim the same invoice again (should fail)"
(Call POST "/claims" $sara @{ invoice_id = $inv.id; statement = "Filing a second claim on the same invoice." } -AllowFail) | ConvertTo-Json

Step "Maya approves WITHOUT a note (should fail if AI didn't say approve)"
(Call POST "/claims/$($claim.id)/decide" $maya @{ decision = "approve" } -AllowFail) | ConvertTo-Json

Step "Maya approves WITH a note"
(Call POST "/claims/$($claim.id)/decide" $maya @{
    decision = "approve"
    note     = "Called the client's office myself. They confirmed delivery but are out of cash."
}) | ConvertTo-Json

Step "Maya approves again (should say already_paid)"
(Call POST "/claims/$($claim.id)/decide" $maya @{ decision = "approve" }) | ConvertTo-Json

Step "Pool after"
$poolAfter = (Call GET "/pool" $sara).pool_balance_cents
Write-Host "   Pool: $poolBefore -> $poolAfter cents (expected -3000)"

Step "Agent log"
$log = Call GET "/agent/actions?limit=5" $maya
$log | Select-Object action, created_at | Format-Table
$paid = $log | Where-Object { $_.action -eq "claim.paid" } | Select-Object -First 1
if ($paid) {
    Write-Host "   Override: $($paid.inputs.override)"
    Write-Host "   Note: $($paid.inputs.admin_note)"
}