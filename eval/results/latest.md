# Kết quả đánh giá – 2026-10-22 23:53

Model: `gpt-4.1-mini` (Agent 1, 2) / `gpt-4.1` (Agent 3, 4); bộ: short; số lần chạy ca ngắn: 1, cuộc họp dài: 1

## Bộ ngắn (tests/fixtures)

Chỉ số tổng hợp trên các ca không phải giới hạn đã biết (số lần chạy mỗi ca: 1):

| Chỉ số | Giá trị | Ngưỡng | Đạt |
| --- | --- | --- | --- |
| Tỷ lệ chốt nhầm | 0.0% (n=2) (tham khảo) | ≤ 5.0% | ✅ |
| Recall quyết định | 100.0% (n=5) (tham khảo) | ≥ 85.0% | ✅ |
| Precision việc cần làm | 60.0% (n=5) (tham khảo) | ≥ 80.0% | ❌ |
| Độ chính xác trích dẫn | 100.0% (n=9) (tham khảo) | ≥ 95.0% | ✅ |
| Owner/deadline bịa | 0 (n=9) (tham khảo) | ≤ 0 | ✅ |
| Trạng thái đúng cho mục chưa chốt | 100.0% (n=3) (tham khảo) | ≥ 80.0% | ✅ |
| Đoạn trích kiểm chứng được | 100.0% (n=31) | ≥ 95.0% | ✅ |
| Owner/deadline có câu nguồn riêng | 100.0% (n=7) (tham khảo) | ≥ 100.0% | ✅ |
| Phạm vi tri thức đúng | không áp dụng (0 mẫu) | ≥ 75.0% | – |
| Quyết định mâu thuẫn không gắn cờ | 0 (n=8) (tham khảo) | ≤ 0 | ✅ |
| Cờ kỳ vọng có mặt (expect_flags_any) | 100.0% (n=1) (tham khảo) | ≥ 100.0% | ✅ |
| Độ ổn định | (chạy với `--repeat 3`) | ≤ 10% | – |

| Ca | Loại | Kết quả |
| --- | --- | --- |
| TC1 | chấm điểm | ❌ 1 lỗi |
| TC2 | chấm điểm | ❌ 1 lỗi |
| TC3 | chấm điểm | ✅ đạt |
| TC4 | chấm điểm | ❌ 1 lỗi |
| TC5 | chấm điểm | ✅ đạt |
| TC6 | giới hạn đã biết | ✅ đạt |
| TC7 | giới hạn đã biết | ✅ đạt |

**TC1**
- Action thừa: [a01] "Lan cung cấp số liệu chi phí cho phương án on-premise" owner=Lan

**TC2**
- Bỏ sót action: "Xem lại phần test tải"

**TC4**
- Action thừa: [a01] "Lan hỏi sếp về ngân sách marketing quý tới rồi báo lại" owner=Lan

Token: vào 145,281 / ra 25,244 qua 98 lần gọi; chi phí ước tính ≈ $0.3744; thời gian 252s.

Ghi chú TC6: hệ thống chỉ gắn cờ `number_check`, không thể phát hiện số sai khi không có audio. TC7: chỉ yêu cầu không có item `confirmed` bịa cho 'phương án đó'.
