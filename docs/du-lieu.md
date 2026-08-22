# Video, frame và dữ liệu

## Ghi chú về fps

30 fps được xác nhận từ chính dữ liệu: ở 25 fps có entry cho ra timestamp vượt
quá độ dài video (`L21_V007` frame 22809 → 912s > 842s), ở 30 fps thì không có entry nào vượt.

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

## Bổ sung frame cho video mới

Server trên cloud **không tự tải video được** — YouTube chặn IP datacenter. Máy bạn
thì tải bình thường. Nên khi có submission dùng video chưa có frame, chạy ở máy:

```bash
python3 sync_frames.py --from-server
```

Nó đọc danh sách submission thẳng từ server, so với bucket, rồi chỉ tải + trích +
đẩy lên phần còn thiếu. Xem trước khi làm:

```bash
python3 sync_frames.py --from-server --dry-run
```

Hoặc chỉ định một CSV cụ thể:

```bash
python3 sync_frames.py submission.csv
```

Cần `KIS_PASSWORD` khi dùng `--from-server`.

**Chỉ chấm điểm mới cần bước này.** Xem video và tua theo frame chạy được với mọi
video trong dataset, không phụ thuộc bucket — player phát thẳng từ YouTube trong
trình duyệt, server không đụng vào.
