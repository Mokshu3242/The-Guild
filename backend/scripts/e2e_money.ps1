param([string]$BaseUrl = "http://127.0.0.1:8000")

function Call($Method, $Path, $Token, $Body = $null) {
    $params = @{
        Method = $Method; Uri = "$BaseUrl$Path"; TimeoutSec = 90
        Headers = @{ Authorization = "Bearer $Token" }
    }
    if ($Body) { $params.Body = ($Body | ConvertTo-Json -Depth 5); $params.ContentType = "application/json" }
    try { return Invoke-RestMethod @params }
    catch {
        Write-Host "FAILED $Method $Path" -ForegroundColor Red
        Write-Host $_.ErrorDetails.Message -ForegroundColor DarkGray
        exit 1
    }
}

function Get-Token($Email, $Password) {
    return (python -m scripts.get_token $Email $Password | Select-Object -Last 1).Trim()
}

function Step($Text) { Write-Host "`n>> $Text" -ForegroundColor Cyan }

$leo = Get-Token "leo@guild.test" "leo@123"

Step "Pool before"
$poolBefore = (Call GET "/pool" $leo).pool_balance_cents
Write-Host "   Pool: $poolBefore cents"

Step "Find Sara"
$me = Call GET "/me" $leo
$members = Call GET "/guilds/$($me.guild_id)/members" $leo
$sara = $members | Where-Object { $_.name -eq "Sara" } | Select-Object -First 1
if (-not $sara) { Write-Host "Sara not found in guild" -ForegroundColor Red; exit 1 }
Write-Host "   Sara: $($sara.id)  PayPal: $($sara.paypal_email)"

Step "Leo posts a job"
$job = Call POST "/jobs" $leo @{
    client_name  = "Paul Payer"
    client_email = "client1-sb@personal.example.com"
    description  = "Landing page copy for a coffee brand, hero plus three sections."
}
Write-Host "   Job: $($job.id)"

Step "Leo assigns Sara"
Call POST "/jobs/$($job.id)/assign" $leo @{ worker_id = $sara.id; match_reason = "Strong copywriter" } | Out-Null

Step "Leo adds a `$100 milestone"
$ms = Call POST "/jobs/$($job.id)/milestones" $leo @{
    title = "Landing page copy"; scope = "Hero + 3 sections"; amount_cents = 10000
}
Write-Host "   Milestone: $($ms.id)"

Step "Leo sends the invoice"
$inv = Call POST "/invoices/milestones/$($ms.id)/send" $leo
Write-Host "   Invoice: $($inv.id)"
Write-Host "   Pay link: $($inv.pay_url)" -ForegroundColor Yellow

Step "Sync before paying (should say not_paid_yet)"
(Call POST "/invoices/$($inv.id)/sync" $leo) | ConvertTo-Json

Write-Host "`nNow open the pay link, log in as client1-sb, and pay." -ForegroundColor Yellow
Start-Process $inv.pay_url
Read-Host "Press Enter after paying"

Step "Sync after paying"
$result = Call POST "/invoices/$($inv.id)/sync" $leo
$result | ConvertTo-Json

Step "Sync again (should say already_paid)"
(Call POST "/invoices/$($inv.id)/sync" $leo) | ConvertTo-Json

Step "Pool after"
$poolAfter = (Call GET "/pool" $leo).pool_balance_cents
Write-Host "   Pool: $poolBefore -> $poolAfter cents (expected +500)"

Step "Leo's earnings"
$earn = Call GET "/me/earnings" $leo
Write-Host "   Leo total: $($earn.total_cents) cents"
$earn.payouts | Select-Object kind, amount, status, paypal_batch_id | Format-Table

Write-Host "Done. Check member3-sb (Sara) for +`$85 and member2-sb (Leo) for +`$10." -ForegroundColor Green