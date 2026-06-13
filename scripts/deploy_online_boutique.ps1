$ErrorActionPreference = "Stop"

kubectl create namespace online-boutique --dry-run=client -o yaml | kubectl apply -f -

$demoDir = Join-Path $PSScriptRoot "..\third_party\microservices-demo"
if (-not (Test-Path $demoDir)) {
  if (-not $env:ONLINE_BOUTIQUE_REPO_URL) {
    throw "Set ONLINE_BOUTIQUE_REPO_URL to the official Online Boutique source URL, or place the source tree at third_party\microservices-demo."
  }
  New-Item -ItemType Directory -Force -Path (Split-Path $demoDir) | Out-Null
  git clone --depth 1 $env:ONLINE_BOUTIQUE_REPO_URL $demoDir
}

kubectl apply -n online-boutique -f (Join-Path $demoDir "release\kubernetes-manifests.yaml")

Write-Host "Online Boutique manifests applied. Check with:"
Write-Host "kubectl get pods -n online-boutique"
