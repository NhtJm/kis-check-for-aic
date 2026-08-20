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
