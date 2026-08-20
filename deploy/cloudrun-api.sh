#!/usr/bin/env bash
# Bat che do rerank qua Agent Router cho service tren Cloud Run.
#
# Doc KIS_API_KEY tu file .env o may ban va day thang vao Secret Manager --
# khoa khong bao gio nam trong image, trong git, hay trong lich su lenh.
#
#   cp .env.example .env     # dien khoa vao
#   ./deploy/cloudrun-api.sh [ten-service] [region]
set -euo pipefail

SERVICE="${1:-kis-check-for-aic}"
REGION="${2:-asia-southeast1}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SECRET="kis-api-key"

[ -f "$ROOT/.env" ] || { echo "Khong thay $ROOT/.env -- chay: cp .env.example .env"; exit 1; }
# shellcheck disable=SC1090
set -a; . "$ROOT/.env"; set +a
: "${KIS_API_KEY:?thieu KIS_API_KEY trong .env}"
: "${KIS_API_BASE:?thieu KIS_API_BASE trong .env}"
: "${KIS_API_MODEL:?thieu KIS_API_MODEL trong .env}"

PROJECT="$(gcloud config get-value project)"
echo "project = $PROJECT   service = $SERVICE"
echo "model   = $KIS_API_MODEL   base = $KIS_API_BASE"
echo "khoa    = ***${KIS_API_KEY: -4}"

echo
read -r -p "Service nay dang PUBLIC. Ai vao cung bam cham diem va tieu credit cua ban. Tiep tuc? [y/N] " ok
[ "$ok" = "y" ] || { echo "da huy"; exit 1; }

gcloud services enable secretmanager.googleapis.com --quiet

if gcloud secrets describe "$SECRET" >/dev/null 2>&1; then
  printf '%s' "$KIS_API_KEY" | gcloud secrets versions add "$SECRET" --data-file=- --quiet
  echo "da them phien ban moi cho secret $SECRET"
else
  printf '%s' "$KIS_API_KEY" | gcloud secrets create "$SECRET" --data-file=- --quiet
  echo "da tao secret $SECRET"
fi

# Cho service account cua Cloud Run quyen doc secret
SA="$(gcloud run services describe "$SERVICE" --region "$REGION" \
      --format='value(spec.template.spec.serviceAccountName)')"
[ -n "$SA" ] || SA="$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')-compute@developer.gserviceaccount.com"
gcloud secrets add-iam-policy-binding "$SECRET" \
  --member="serviceAccount:$SA" --role=roles/secretmanager.secretAccessor --quiet >/dev/null
echo "da cap quyen doc secret cho $SA"

# --update-env-vars chu KHONG phai --set-env-vars: --set thay toan bo env var
# cua service, xoa mat KIS_VIDEO_DIR / KIS_FETCH da dat truoc do.
gcloud run services update "$SERVICE" --region "$REGION" --quiet \
  --update-env-vars "KIS_API_BASE=$KIS_API_BASE,KIS_API_MODEL=$KIS_API_MODEL" \
  --update-secrets "KIS_API_KEY=$SECRET:latest"

echo
echo "Xong. Kiem tra:"
echo "  curl -s $(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')/api/status"
echo "Muon go khoa ra sau nay:"
echo "  gcloud run services update $SERVICE --region $REGION --remove-secrets KIS_API_KEY"
