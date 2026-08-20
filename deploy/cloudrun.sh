#!/usr/bin/env bash
# Deploy len Google Cloud Run.
#
# Lam mot lan truoc do (can tai khoan cua ban):
#   gcloud auth login
#   gcloud projects create <PROJECT_ID>          # hoac dung project san co
#   gcloud config set project <PROJECT_ID>
#   # bat billing cho project o https://console.cloud.google.com/billing
#
# Roi:
#   ./deploy/cloudrun.sh [ten-service] [region]
set -euo pipefail

SERVICE="${1:-kis-check-for-aic}"
REGION="${2:-asia-southeast1}"          # Singapore, gan Viet Nam nhat
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

PROJECT="$(gcloud config get-value project 2>/dev/null)"
[ -n "$PROJECT" ] && [ "$PROJECT" != "(unset)" ] || {
  echo "Chua chon project. Chay: gcloud config set project <PROJECT_ID>"; exit 1; }
echo "project = $PROJECT"
echo "service = $SERVICE   region = $REGION"

echo "bat cac API can thiet ..."
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
                       artifactregistry.googleapis.com --quiet

# Cloud Build doc Dockerfile o goc thu muc nguon, nen don rieng mot thu muc
# chi chua dung nhung gi can -- khong mang videos/, media-info/, .env len.
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
cp "$ROOT"/{serve.py,score_query.py,scorers.py,api_backend.py,query_expand.py,video_cache.py,compare.py} "$TMP/"
cp "$ROOT"/{index.html,kis-viewer.html,media-index.json,requirements.txt,requirements-local.txt} "$TMP/"
cp "$ROOT/deploy/Dockerfile.cloudrun" "$TMP/Dockerfile"
echo "day $(ls "$TMP" | wc -l | tr -d ' ') file de Cloud Build dung image ..."

# Cloud Build dung tren ha tang amd64 cua Google -- dung kien truc Cloud Run can,
# khong vuong chuyen build tren may Apple Silicon ra arm64.
gcloud run deploy "$SERVICE" \
  --source "$TMP" \
  --region "$REGION" \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 2 \
  --timeout 900 \
  --concurrency 2 \
  --min-instances 0 \
  --max-instances 2 \
  --port 8080 \
  --quiet

URL="$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')"
echo
echo "Xong: $URL"
echo "Kiem tra:  curl -s $URL/api/status"
echo
echo "Muon bat che do rerank qua Agent Router thi them bien moi truong:"
echo "  gcloud run services update $SERVICE --region $REGION \\"
echo "    --set-env-vars KIS_API_BASE=https://agentrouter.org/v1,KIS_API_MODEL=claude-opus-5 \\"
echo "    --set-secrets KIS_API_KEY=kis-api-key:latest"
echo "(dat khoa bang Secret Manager, dung --set-env-vars cho khoa)"
