# KIS Submission Checker

Công cụ cho nhóm cùng kiểm tra kết quả Known-Item Search của AIC: mở đúng video
YouTube tại đúng frame, chia việc theo người, và dùng AI lọc trước những kết quả
gần như chắc chắn sai.

## Chạy ở máy

```bash
pip install -r requirements-local.txt
python3 src/serve.py
```

Rồi mở http://localhost:8777/login.html

Đặt `KIS_PASSWORD` nếu muốn yêu cầu mật khẩu chung; bỏ trống thì ai cũng vào được.

## Cấu trúc thư mục

Chia theo **ai dùng file đó**, không theo loại file:

| Thư mục | Chứa gì | Chạy ở đâu |
|---|---|---|
| `src/` | server, chấm điểm, lưu trữ nhóm | trên server |
| `web/` | trang gửi tới trình duyệt | trình duyệt |
| `templates/` | bản mẫu để build ra `web/index.html` | lúc build |
| `tools/` | tải video, trích frame, đồng bộ | máy bạn |
| `deploy/` | Dockerfile, script triển khai | lúc deploy |
| `docs/` | tài liệu | — |
| `data/` | video, frame, media-info, dữ liệu nhóm | không lên git |

`data/` bị gitignore vì nặng (video ~4.6GB). Sinh lại bằng `tools/fetch_videos.py`.

## Các trang

| Trang | Ai vào được |
|---|---|
| `login.html` | mọi người — chọn tên bằng nút, nhập mật khẩu chung |
| `hub.html` | mọi người — điều hướng + việc được giao |
| `index.html` | mọi người — kiểm tra submission, đánh dấu đúng/sai |
| `upload.html` | mọi người — nộp CSV hoặc cả bộ bằng ZIP |
| `queries.html` | **admin** — dán đề thi, tách query, gắn CSV |
| `admin.html` | **admin** — vai trò, chia việc, chuyển vòng thi |

## Tài liệu

- [Sử dụng hằng ngày](docs/su-dung.md) — chia việc, đánh dấu, gộp kết quả
- [Chấm điểm bằng AI](docs/cham-diem.md) — SigLIP, rerank, chọn model, TRAKE
- [Video, frame và dữ liệu](docs/du-lieu.md) — vì sao server chỉ cần frame
- [Triển khai](docs/deploy.md) — Cloud Run, chọn host, chi phí
- [Phát triển](docs/phat-trien.md) — build lại giao diện

## Vài điều đã đo, không phải phỏng đoán

- **fps = 30**, xác nhận từ chính dữ liệu (ở 25 fps có entry vượt quá độ dài video)
- **Query tiếng Anh xếp hạng tốt hơn tiếng Việt** — tiếng Việt dồn cả nhóm đầu vào
  98-100% không tách được
- **`gpt-4o` rẻ hơn `gpt-4o-mini` cho ảnh** — mini nhân token ảnh lên ~33 lần
- **Chia việc theo video, đừng chia theo dòng** — giảm 4 lần số lần nạp video
- **YouTube chặn tải từ IP datacenter** — nên server dùng frame trích sẵn
