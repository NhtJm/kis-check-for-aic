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

| Host | RAM free tier | SigLIP chạy được? | Ghi chú |
|---|---|---|---|
| **HF Spaces** | ~16GB | **có** | Dockerfile ở `deploy/Dockerfile.spaces` |
| Render free | 512MB | không | ép dùng API, ngủ sau 15 phút |
| Railway | — | — | không còn free tier thật, tối thiểu ~$5/tháng |

HF Spaces là lựa chọn tốt nhất cho việc này: đủ RAM chạy SigLIP nên **không tốn
tiền API**, và ngủ sau 48h chứ không phải 15 phút.

```bash
./deploy/setup-spaces.sh <user>/<space-name>
```

Khoá API (nếu muốn dùng chế độ rerank) đặt ở **Settings → Variables and secrets**
của Space, không đưa `.env` lên.
