# Triển khai

## Deploy lên container host

Bản GitHub Pages là **trang tĩnh** — không có server nên không có chỗ đặt `.env`,
và thanh query tự ẩn. Muốn chấm điểm trên bản deploy thì cần host chạy được Python.

Repo đã có sẵn `Dockerfile` và `render.yaml`.

### Ba ràng buộc đã được xử lý sẵn

**RAM.** SigLIP cần ~1.5GB, free tier thường chỉ 512MB. `Dockerfile` vì vậy đặt
`KIS_BACKENDS=api` và **không cài torch** — image còn ~400MB thay vì ~3GB.
Server từ chối thẳng request xin chạy `siglip`, không để nó OOM giữa chừng.

**Video.** 380MB không bán vào image được, nên `KIS_FETCH=1` bật chế độ tải theo
yêu cầu: thiếu video nào thì `yt-dlp` kéo bản 360p về `/tmp`, dùng xong giữ lại
làm cache, vượt `KIS_VIDEO_CACHE_MB` thì xoá cái lâu không đụng nhất.
Lần đầu chạm một video mất ~5-20s, các lần sau tức thì.

Luôn tải **nguyên video** chứ không cắt đoạn — cắt đoạn làm frame đánh số lại từ 0
và chỗ cắt bám theo keyframe, khiến chỉ số frame lệch đi.

**media-info.** Thư mục 873 file không lên git, nên `build_viewer.py` xuất kèm
`media-index.json` (192KB) — server dùng file này để tra video ID ra link YouTube.
Nhớ chạy lại `build_viewer.py` và commit `media-index.json` khi dataset đổi.

### Các bước

1. Trên Render: **New → Web Service**, trỏ vào repo này, chọn runtime **Docker**.
2. Vào tab **Environment**, thêm ba biến (đặt ở dashboard, **không** đưa `.env` lên git):

   | Key | Value |
   |---|---|
   | `KIS_API_BASE` | `https://agentrouter.org/v1` |
   | `KIS_API_KEY` | khoá của bạn |
   | `KIS_API_MODEL` | `claude-opus-5` |

3. Deploy. Kiểm tra `/api/status` — `"api": true` và `"backends": ["api"]` là đúng.

Free tier của Render ngủ sau 15 phút không ai dùng, request đầu sau đó mất ~30s để
đánh thức, và mỗi lần ngủ dậy là `/tmp` trống nên video phải tải lại.

### Chi phí

Theo công thức của Agent Router `(prompt + completion × completion_ratio) / 500000`,
với `claude-opus-5` (ratio 1, completion ratio 5), cửa sổ ±90 frame bước 30:

| Chế độ | Số request | Ước tính mỗi lần chạy 100 dòng |
|---|---|---|
| `hybrid` (chỉ chạy được ở local) | ~140 | ~$0.15 |
| `api` | ~700 | ~$0.77 |

Muốn rẻ hơn thì giảm cửa sổ: `--window 30 --step 30` còn 3 frame mỗi dòng thay vì 7.

## Deploy: chọn host nào

| Host | Free? | SigLIP chạy được? | Ghi chú |
|---|---|---|---|
| **Google Cloud Run** | có | **có** | 2Gi RAM là đủ, scale về 0 |
| HF Spaces (Docker) | **không** | có | Docker Space cần PRO ~$9/tháng |
| Render free | có | không | 512MB, ép dùng API, ngủ sau 15 phút |
| Railway | không | — | tối thiểu ~$5/tháng |

Cloud Run là lựa chọn tốt nhất: free tier thật, đủ RAM chạy SigLIP nên **không
tốn tiền API**, và scale về 0 khi không ai dùng.

```bash
gcloud auth login
gcloud config set project <PROJECT_ID>
./deploy/cloudrun.sh
```

Đo thực tế trong container 2Gi: 30 frame mất ~40s kể cả tải video, RAM đỉnh 460MB.

```bash
huggingface-cli login
python3 deploy/push_space.py <user>/<space-name>
```

Khoá API (nếu muốn dùng chế độ rerank) đặt ở **Settings → Variables and secrets**
của Space, không đưa `.env` lên.

### Lưu ý khi chạy trên Space

Space free chạy **CPU**, không có MPS — chấm điểm chậm hơn máy bạn nhiều lần.
Vì vậy Dockerfile đặt `KIS_MAX_FRAMES=350`: request lớn hơn bị từ chối kèm lời
nhắc thu nhỏ cửa sổ, thay vì để bạn ngồi chờ rồi ăn gateway timeout.

Với 100 dòng thì cửa sổ `±30 bước 30` (300 frame) là vừa. Muốn quét cửa sổ rộng
hơn thì chạy ở máy bằng `python3 serve.py` — ở đó không có giới hạn.

**Nếu bạn đặt khoá API làm secret trên Space public:** ai vào cũng bấm chấm điểm
được và tiêu credit của bạn. Hoặc để Space private, hoặc đừng đặt khoá API lên đó
và chỉ dùng SigLIP (vốn miễn phí và là lý do chọn Spaces).

### Hai lỗi chỉ lộ ra trong container

Cả hai đều chạy tốt trên máy dev nhưng chết trong image sạch — nếu chưa build thử
thì sẽ phát hiện lúc đã deploy:

- **`protobuf`** — `SiglipTokenizer` cần nó, máy dev thường có sẵn qua gói khác.
  Đã thêm vào `requirements-local.txt`.
- **transformers 5.x** — bản 5 đổi `get_text_features` sang trả về object thay vì
  tensor (`'BaseModelOutputWithPooling' object has no attribute 'norm'`). Máy dev
  đang ở 4.51, container cài mới ra 5.15. `scorers._feat()` giờ xử lý được cả hai
  bản thay vì ghim phiên bản.

Ngoài ra `pip install torch` trên Linux mặc định kéo bản CUDA kèm ~2-3GB driver
NVIDIA vô dụng trên host CPU — Dockerfile ép về index CPU.

### YouTube chặn tải từ cloud — video phải nằm ở Cloud Storage

Chế độ `KIS_FETCH=1` (tải video theo yêu cầu) **chỉ chạy được ở máy nhà**. Trên
mọi cloud host, yt-dlp bị YouTube chặn:

```
ERROR: [youtube] <id>: Sign in to confirm you're not a bot.
```

Đây là chặn theo IP datacenter, không sửa được bằng code. Phần **xem video vẫn
chạy bình thường** vì player nằm trong trình duyệt người xem, không phải trên server.

Cách xử lý: đẩy video lên bucket rồi mount vào Cloud Run.

```bash
gcloud storage buckets create gs://<BUCKET> --location=asia-southeast1 --uniform-bucket-level-access
gcloud storage rsync videos gs://<BUCKET> --recursive

gcloud run services update kis-check-for-aic --region asia-southeast1 \
  --add-volume=name=vids,type=cloud-storage,bucket=<BUCKET>,readonly=true \
  --add-volume-mount=volume=vids,mount-path=/videos \
  --update-env-vars KIS_VIDEO_DIR=/videos,KIS_FETCH=0
```

Thêm video mới cho submission khác thì `fetch_videos.py` ở máy rồi `rsync` lên bucket.

### Gọi GPT / Claude qua Agent Router trên Cloud Run

Cloud Run **không đọc file `.env`** — container là ephemeral, và nhét khoá vào
image thì ai kéo image cũng đọc được. Khoá phải nằm ở Secret Manager:

```bash
cp .env.example .env      # điền KIS_API_KEY, đặt KIS_API_MODEL=gpt-5.6-sol
./deploy/cloudrun-api.sh
```

Script đọc `.env` ở máy bạn, đẩy khoá thẳng vào Secret Manager, cấp quyền đọc cho
service account, rồi gắn vào service. Khoá không đi qua image, không vào git.

**Cân nhắc trước khi bật:** service đang public, nên ai vào cũng bấm chấm điểm
được và tiêu credit của bạn. Nếu chỉ cần SigLIP (vốn miễn phí và đủ dùng) thì
đừng gắn khoá lên đó — chạy rerank ở máy khi cần.
