$ErrorActionPreference = "Stop"

$keys = @{}
Get-Content -Path "C:\Users\rehaa\OneDrive\Desktop\OSSOMEHACKS\SentinelShield\.env" | ForEach-Object {
    if ($_ -match "^([^#\s][^=]+)=['""]?(.*?)['""]?$") {
        $keys[$matches[1]] = $matches[2]
    }
}

$armoriqKey = $keys["ARMORIQ_API_KEY"]
$geminiKey  = $keys["GEMINI_API_KEY"]
$alpacaId   = $keys["ALPACA_API_KEY_ID"]
$alpacaSec  = $keys["ALPACA_SECRET_KEY"]

Write-Host "Installing OpenClaw..."
npm install -g openclaw@latest

# Ensure npm global bin is in PATH for this session
$npmGlobalPath = (npm root -g).Replace("node_modules", "")
$env:PATH = "$npmGlobalPath;" + $env:PATH

Write-Host "Creating OpenClaw configuration..."
$openclawDir = Join-Path $env:USERPROFILE ".openclaw"
$workspaceDir = Join-Path $openclawDir "workspace"
$skillsDir = Join-Path $workspaceDir "skills"
New-Item -ItemType Directory -Force -Path $skillsDir | Out-Null

$openclawConfig = @"
{
  "agent": {
    "model": "google/gemini-pro"
  },
  "env": {
    "GEMINI_API_KEY": "$geminiKey",
    "ALPACA_API_KEY_ID": "$alpacaId",
    "ALPACA_SECRET_KEY": "$alpacaSec"
  },
  "plugins": {
    "enabled": true,
    "allow": ["armorclaw"],
    "entries": {
      "armorclaw": {
        "enabled": true,
        "config": {
          "enabled": true,
          "policyStorePath": "~/.openclaw/armoriq.policy.json",
          "apiKey": "$armoriqKey"
        }
      }
    }
  }
}
"@
Set-Content -Path (Join-Path $openclawDir "openclaw.json") -Value $openclawConfig -Encoding UTF8

$armoriqPolicy = @"
{
  "allow_tools": ["alpaca_buy", "alpaca_sell", "alpaca_get_account", "alpaca_get_positions"],
  "deny_tools": ["bash", "write", "exec", "browser", "nodes"],
  "financial_constraints": {
    "max_trade_usd": 2000,
    "min_trade_usd": 1,
    "allowed_tickers": ["AAPL", "MSFT", "GOOGL", "AMZN"],
    "allowed_actions": ["BUY", "SELL"]
  }
}
"@
Set-Content -Path (Join-Path $openclawDir "armoriq.policy.json") -Value $armoriqPolicy -Encoding UTF8

Write-Host "Installing ArmorClaw plugin..."
openclaw plugins install @armoriq/armorclaw

Write-Host "Setup Completed Successfully!"
