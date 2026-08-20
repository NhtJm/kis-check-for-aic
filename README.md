# KIS Submission Checker

Công cụ kiểm tra nhanh file submission Known-Item Search (AIC) bằng cách phát
đúng video YouTube tại đúng thời điểm suy ra từ số frame.

**Dùng ngay:** https://nhtjm.github.io/kis-check-for-aic/

## Cách dùng

1. Bấm **Chọn file CSV…**, chọn file submission, rồi bấm **Nạp**
   (hoặc kéo thả thẳng file vào trang — nạp luôn).
2. CSV mỗi dòng: `L21_V015,25725` — mã video, số frame. Dòng header được bỏ qua.
3. Frame đổi ra giây theo **fps** ở thanh trên (mặc định `30`, sửa được).
4. Duyệt bằng `↑`/`↓`, đánh dấu `1` đúng · `2` sai · `3` chưa chắc.
   Mặc định video **đứng sẵn ở đúng frame**, bấm mới chạy — bật **Tự phát**
   nếu muốn chọn kết quả là phát ngay. Lựa chọn này được nhớ lại.
5. **Xuất CSV** để lấy lại bảng kèm timestamp và đánh giá.

Đánh dấu lưu trong `localStorage` theo tên file, đóng tab mở lại vẫn còn.

## Build lại

Trang là một file HTML tự chứa, đã nhúng sẵn index `media-info/` (873 video)
nên chạy được offline trừ phần player YouTube.

```bash
python3 build_viewer.py media-info kis-viewer.html [submission.csv]
```

Tham số CSV thứ ba là tuỳ chọn — nếu có, file đó được nạp sẵn khi mở trang, và
build sẽ hỏi YouTube xem video nào đã bị gỡ / để riêng tư. Thêm `--no-check` để bỏ bước đó.

## Ghi chú về fps

30 fps được xác nhận từ chính dữ liệu: ở 25 fps có entry cho ra timestamp vượt
quá độ dài video (`L21_V007` frame 22809 → 912s > 842s), ở 30 fps thì không có entry nào vượt.

## Chấm điểm query bằng AI

Nhập câu query, hệ thống lấy frame thật ra và chấm mức khớp theo %.
Chỉ chạy khi bạn mở bằng `serve.py` ở máy mình — bản GitHub Pages là trang tĩnh
nên thanh query tự ẩn.

```bash
pip install yt-dlp sentencepiece
python3 fetch_videos.py submission.csv    # tải video 360p về thư mục videos/
python3 serve.py                          # rồi mở http://localhost:8777/
```

Hoặc chạy thẳng ngoài dòng lệnh:

```bash
python3 score_query.py --csv submission.csv --query "bốn phi hành gia mặc áo đen"
```

Với mỗi dòng, script lấy thêm vài frame trước/sau (`--window 90 --step 30`
= ±3 giây, mỗi giây một frame) rồi báo: điểm tại đúng frame đó, điểm cao nhất
trong cửa sổ, và lệch bao nhiêu frame — để biết frame chỉ hơi trượt hay sai hẳn.

### Ba chế độ chấm

| Chế độ | Cách chạy | Tốc độ | Chi phí |
|---|---|---|---|
| `siglip` | SigLIP đa ngữ chạy local trên MPS | ~700 frame / 26s | miễn phí |
| `hybrid` | SigLIP lọc trước, VLM chấm lại top 20 | thêm ~140 request | thấp |
| `api` | VLM chấm toàn bộ frame | ~700 request | cao |

### Cấu hình API

Khoá đọc từ file `.env` ở thư mục gốc dự án, hoặc từ biến môi trường.
`.env` đã nằm trong `.gitignore` — **không bao giờ commit nó**.

```bash
cp .env.example .env      # rồi mở ra điền khoá
python3 api_backend.py    # kiểm tra: gọi thử 1 ảnh mẫu
```

```ini
KIS_API_BASE=https://agentrouter.org/v1
KIS_API_KEY=sk-...
KIS_API_MODEL=claude-opus-5
```

Biến môi trường thật luôn thắng `.env`, nên khi deploy thì đặt env var ở
dashboard của host thay vì mang file `.env` lên.

Khi đủ ba giá trị, `serve.py` tự mở khoá hai chế độ `hybrid` và `api` trong UI.

### Đọc con số thế nào cho đúng

SigLIP huấn luyện bằng sigmoid loss nên `sigmoid(scale·cos + bias)` là **xác suất
khớp tuyệt đối** — khác CLIP vốn chỉ so tương đối được. Nó tách rất tốt khớp /
không khớp: trong lần chạy thử, query đúng cho 99.9%, "một tô phở bò" 0.00%,
"cầu thủ sút bóng" 0.00%.

Nhưng nó **bão hoà ở đỉnh**: nhiều frame thật sự khớp đều đội trần ~100% và không
xếp hạng được với nhau. Vì vậy cột `cosine` được xuất kèm và dùng để phá thế hoà —
nó còn nguyên độ phân giải. Rê chuột lên badge % để xem.

Câu query nên viết **tiếng Việt**: cùng một nội dung, bản tiếng Việt cho 99.9%
còn bản tiếng Anh chỉ 13.2%.

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

## Xếp hạng lại và đo chất lượng

Điểm % không nói lên chất lượng — **thứ hạng của frame đúng** mới nói lên. Dùng
`compare.py` để đo, với `--truth` là dòng bạn biết chắc là đúng:

```bash
python3 compare.py --csv submission.csv \
  --query "câu query tiếng Việt" \
  --en "English translation" \
  --truth L21_V015,25725
```

Nó chạy lần lượt các cấu hình và báo frame đúng rơi vào hạng mấy ở từng cấu hình.

### Xếp lại vòng hai

```bash
# VLM qua agent router xếp lại 30 dòng đầu — nhanh, chỉ ~30 request
python3 score_query.py --csv sub.csv --query "..." --rerank api --rerank-topk 30

# hoặc jina-clip-v2 chạy local — không tốn tiền nhưng chậm hơn nhiều
python3 score_query.py --csv sub.csv --query "..." --rerank jinaai/jina-clip-v2
```

Nhóm đã rerank **luôn xếp trên** nhóm còn lại. Đây là chủ ý: điểm của hai model
khác thang đo nhau, trộn chung rồi sort là sai thứ tự. Thứ tự chuẩn nằm ở trường
`rank_final`, không phải ở `score`.

Mặc định VLM chỉ chấm đúng frame đó (offset 0) cho nhanh và rẻ; model chạy local
thì quét cả cửa sổ. Đổi bằng `--rerank-window N`.

### Gộp nhiều biến thể câu query

```bash
python3 score_query.py --csv sub.csv --query "..." --expand 6
```

Nhờ LLM dịch sang tiếng Anh và diễn đạt lại thành N biến thể rồi gộp vector chữ
(`--agg mean_emb`, cách gộp kinh điển của CLIP). Cần cấu hình API.

**Gộp không phải lúc nào cũng tốt hơn.** Trong một phép đo (n=1, query của tôi
chứ không phải của bạn): tiếng Anh thuần đưa frame đúng lên hạng 1, tiếng Việt
thuần hạng 2, còn gộp VI+EN lại tụt về hạng 2. Trung bình vector kéo kết quả về
phía biến thể yếu hơn. Hãy tự đo bằng `compare.py` trên query thật của bạn.

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

## Chọn model cho rerank: đo thật, đừng đoán

Trực giác "chọn model nhẹ cho rẻ" **sai với ảnh**. `gpt-4o-mini` nhân token ảnh
lên ~33 lần để bù giá token rẻ, nên cuối cùng đắt hơn cả `gpt-4o`.

Số đo thật, một frame 512px, `detail:"low"`, chấm frame có phi hành gia áo đen:

| Model | token/ảnh | $/frame | 700 frame | Chấm |
|---|---|---|---|---|
| **gpt-4o** | **117** | **$0.00034** | **$0.24** | 90 ✓ |
| gpt-4o-mini | 2865 | $0.00043 | $0.30 | 90 ✓ |
| gpt-4o-mini (detail auto) | 8532 | $0.00128 | $0.90 | 90 ✓ |
| gpt-4.1-mini | 265 | $0.00011 | $0.08 | 30 ✗ |
| gpt-4.1-nano | 386 | $0.00004 | $0.03 | 10 ✗ |

Hai kết luận: `detail:"low"` giảm 3 lần chi phí mà đáp án không đổi (đã bật mặc
định trong `api_backend.py`), và hai model nano/mini rẻ thật nhưng **chấm sai** —
cho 30 và 10 đúng cái frame mà gpt-4o và gpt-4o-mini đều chấm 90.

Kiểm tra trước khi chấm cả bộ, chỉ tốn một lệnh gọi:

```bash
python3 deploy/test_api.py           # gọi đúng đường chạy thật, in usage + chi phí
python3 deploy/test_api.py --list    # xem model nào dùng được
```

### Rerank có tác dụng thật

Đo trên submission 100 dòng, query tiếng Việt, `--rerank api --rerank-topk 20`:

| | Trước rerank (SigLIP) | Sau rerank (gpt-4o) |
|---|---|---|
| `L21_V015,25725` (frame đúng) | hạng 2 | **hạng 1**, chấm 1.00 |
| `L21_V024,20734` (cảnh gần giống) | hạng 1 | hạng 2, chấm 0.50 |
| 18 dòng còn lại | 90-99%, không tách được | 0.00 |

SigLIP bão hoà ở đỉnh nên không xếp hạng nổi trong nhóm đầu; VLM tách dứt khoát.
Tổng 32.7s (689 frame SigLIP miễn phí + 20 lệnh gọi API ~$0.017).

## Agent Router không dùng được — và vì sao

Router này chỉ chấp nhận một số client được họ hỗ trợ chính thức. Script tự viết
gọi vào bị từ chối:

```
401 unauthorized client detected
使用官方里支持的这些客户端 / Please use the officially supported harnesses
```

Đã thử và loại trừ hết: khoá mới, prompt tiếng Anh, SDK `openai` chính thức,
User-Agent chuẩn, mọi model. **Kể cả `GET /models`** — endpoint không có nội dung
gì để lọc — cũng trả 401. Đây là chính sách kiểm soát truy cập của họ, không phải
lỗi cấu hình, và không nên tìm cách lách.

Có một chi tiết đáng ghi lại: ban đầu request tiếng Việt trả `400 content-blocked`
còn tiếng Anh trả `401`. Lý do là **bộ lọc nội dung chạy trước khâu xác thực** —
request tiếng Việt bị chặn trước khi kịp chạm tới auth, nên che mất vấn đề thật
nằm ở dưới. Nếu chỉ nhìn lỗi tiếng Việt thì sẽ đi sai hướng.

Dùng OpenAI trực tiếp. Đã đo: chạy tốt, $0.00073/frame với `gpt-4o`.

## Viết query bằng tiếng Anh

Đo trên cùng một submission, cùng frame đúng (`L21_V015,25725`):

| Hạng | Query tiếng Anh | Query tiếng Việt |
|---|---|---|
| 1 | **29.77%** ← frame đúng | 99.9% ← frame đúng |
| 2 | 23.44% | 100.0% |
| 3 | 0.17% | 99.7% |
| 4 | 0.06% | 98.4% |

Tiếng Việt dồn cả nhóm đầu vào 98-100%, không xếp hạng được với nhau. Tiếng Anh
tách dứt khoát. Đây là lý do thật để viết query tiếng Anh — không phải vì model
"hiểu tiếng Anh hơn", mà vì nó cho **độ tách** dùng được.

## Server chỉ cần frame, không cần video

Đây là cách chạy nên dùng khi deploy. Trích sẵn các frame mà submission cần rồi
đẩy lên bucket — server không đụng tới file video, cũng không đụng tới YouTube.

```bash
python3 fetch_videos.py submission.csv                    # tải video (chỉ ở máy)
python3 extract_frames.py --csv submission.csv --window 90 --step 30
gcloud storage rsync frames gs://<BUCKET>/frames --recursive
```

Chênh lệch rất lớn — đo trên `submission-kis-3.csv` (100 dòng, 57 video):

| | Dung lượng | Thời gian đẩy lên |
|---|---|---|
| Video đầy đủ | 2.2 GB | vài phút |
| 700 frame JPEG | **31 MB** | **11 giây** |

Nhỏ hơn 70 lần. Trích mất 4.5 giây.

Trích ở cửa sổ rộng nhất bạn định dùng (`--window 90 --step 30` = 7 frame/dòng);
cửa sổ hẹp hơn lúc chấm là tập con nên vẫn chạy. Thiếu frame nào thì bỏ qua frame
đó chứ không hỏng cả lượt.

`score_query.py` ưu tiên `frames/` trước, chỉ lùi về đọc video khi thiếu. Trên
Cloud Run đặt `KIS_FRAME_DIR=/videos/frames`.
