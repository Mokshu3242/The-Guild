$BaseUrl = "http://127.0.0.1:8000"
$OldInvoice = "c7e40310-eae1-4453-ae73-9a399f574bec"
$WaitingClaim = "cb4ba593-8ee9-4e1c-b7d5-bba7f2360c0c"

function Get-Token($Email, $Password) {
    return (python -m scripts.get_token $Email $Password | Select-Object -Last 1).Trim()
}
function Call($Method, $Path, $Token, $Body = $null) {
    $params = @{ Method = $Method; Uri = "$BaseUrl$Path"; TimeoutSec = 120; Headers = @{ Authorization = "Bearer $Token" } }
    if ($Body) { $params.Body = ($Body | ConvertTo-Json); $params.ContentType = "application/json" }
    return Invoke-RestMethod @params
}

$leo  = Get-Token "leo@guild.test"  "leo@123"
$maya = Get-Token "maya@guild.test" "maya@123"

Write-Host "`n1. Pool right now: $((Call GET '/pool' $leo).pool_balance_cents) cents" -ForegroundColor Cyan

Write-Host "`n2. Opening Gary's old invoice. Log in as client2-sb and PAY it." -ForegroundColor Yellow
Start-Process (Call GET "/invoices/$OldInvoice" $leo).pay_url
Read-Host "   Press Enter after paying"

Write-Host "`n3. Checking with PayPal..." -ForegroundColor Cyan
Call POST "/invoices/$OldInvoice/sync" $leo | ConvertTo-Json
Write-Host "   Pool now: $((Call GET '/pool' $leo).pool_balance_cents) cents (expected 3800)"

Write-Host "`n4. Maya approves Sara's waiting claim, with a note" -ForegroundColor Cyan
Call POST "/claims/$WaitingClaim/decide" $maya @{
    decision = "approve"
    note     = "Called the client's office myself. They confirmed delivery but are out of cash."
} | ConvertTo-Json

Write-Host "`n5. Final pool: $((Call GET '/pool' $leo).pool_balance_cents) cents (expected 800)" -ForegroundColor Green