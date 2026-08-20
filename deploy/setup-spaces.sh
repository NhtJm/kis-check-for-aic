#!/usr/bin/env bash
# Dua ban nay len Hugging Face Spaces.
#   1) Tao Space moi: https://huggingface.co/new-space  (SDK = Docker, Blank)
#   2) Chay script nay voi ten space cua ban
# Vi du:  ./deploy/setup-spaces.sh NhtJm/kis-check-for-aic
set -euo pipefail
SPACE="${1:?Dung: ./deploy/setup-spaces.sh <user>/<space-name>}"
TMP="$(mktemp -d)"

git clone "https://huggingface.co/spaces/$SPACE" "$TMP"
cp *.py index.html kis-viewer.html media-index.json requirements.txt requirements-local.txt "$TMP/"
cp deploy/Dockerfile.spaces "$TMP/Dockerfile"
cp deploy/README-spaces.md  "$TMP/README.md"

cd "$TMP"
git add -A
git commit -m "KIS submission checker"
git push
echo
echo "Xong. Space: https://huggingface.co/spaces/$SPACE"
echo "Neu muon dung che do API, vao Settings > Variables and secrets cua Space"
echo "va them KIS_API_BASE, KIS_API_KEY, KIS_API_MODEL."
