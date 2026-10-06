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

$maya = Get-Token "maya@guild.test" "maya@123"
$sara = Get-Token "sara@guild.test" "sara@123"

Step "Pool before"
$before = Call GET "/pool" $sara
$before | ConvertTo-Json

Step "Maya sets up the plan (admin)"
(Call POST "/pool/plan" $maya) | ConvertTo-Json

Step "Sara subscribes"
$sub = Call POST "/pool/subscribe" $sara
Write-Host "   Subscription: $($sub.paypal_subscription_id)  Status: $($sub.status)"
Write-Host "   Approve link: $($sub.approve_url)" -ForegroundColor Yellow

Step "Subscribing again returns the same pending link"
$again = Call POST "/pool/subscribe" $sara
Write-Host "   Same id: $($again.paypal_subscription_id -eq $sub.paypal_subscription_id)"

Write-Host "`nOpen the link, log in as member3-sb (Sara's PayPal), and approve." -ForegroundColor Yellow
Write-Host "Then wait for the webhook lines in the server terminal." -ForegroundColor Yellow
Start-Process $sub.approve_url
Read-Host "Press Enter after approving"

Step "Sync subscription"
(Call POST "/pool/subscription/sync" $sara) | ConvertTo-Json

Step "Sync again (newly_credited should be 0)"
(Call POST "/pool/subscription/sync" $sara) | ConvertTo-Json

Step "Pool after"
$after = Call GET "/pool" $sara
$after | ConvertTo-Json
Write-Host "   Pool: $($before.pool_balance_cents) -> $($after.pool_balance_cents) cents (expected +1000)"

Step "Latest pool transactions"
(Call GET "/pool/transactions" $sara) | Select-Object -First 3 source, amount, external_ref | Format-Table