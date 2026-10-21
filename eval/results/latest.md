# Kết quả đánh giá – 2026-10-21 11:29

Model: `gpt-4.1-mini` (Agent 1, 2) / `gpt-4.1` (Agent 3, 4); số lần chạy mỗi ca: 3

Chỉ số tổng hợp trên các ca không phải giới hạn đã biết (TC1–TC5):

| Chỉ số | Giá trị | Ngưỡng | Đạt |
| --- | --- | --- | --- |
| Tỷ lệ chốt nhầm | 0.0% | ≤ 5.0% | ✅ |
| Recall quyết định | 100.0% | ≥ 85.0% | ✅ |
| Precision việc cần làm | 60.0% | ≥ 80.0% | ❌ |
| Độ chính xác trích dẫn | 100.0% | ≥ 95.0% | ✅ |
| Owner/deadline bịa | 1 | ≤ 0 | ❌ |
| Độ ổn định (đổi trạng thái) | 0.0% | ≤ 10.0% | ✅ |

| Ca | Loại | Kết quả |
| --- | --- | --- |
| TC1 | chấm điểm | ✅ đạt |
| TC2 | chấm điểm | ❌ 1 lỗi |
| TC3 | chấm điểm | ❌ 3 lỗi |
| TC4 | chấm điểm | ✅ đạt |
| TC5 | chấm điểm | ❌ 1 lỗi |
| TC6 | giới hạn đã biết | ✅ đạt |
| TC7 | giới hạn đã biết | ❌ 1 lỗi |

## Chi tiết ca sai

**TC2**
- Bỏ sót action: "Xem lại phần test tải"

**TC3**
- Lịch sử thiếu "Ra mắt beta ngày 1/11" superseded trong "Ra mắt bản beta ngày 15/11"
- Action thừa: [a01] "Nam hỗ trợ phỏng vấn vòng kỹ thuật nếu cần" owner=Nam
- Action thừa: [a02] "Khởi động lại server staging" owner=Minh

**TC5**
- deadline bịa: "Tuần sau chốt dùng React cho front-end" deadline='tuần sau'

**TC7**
- Action thừa: [a02] "Báo bên toà nhà về máy lạnh hỏng" owner=Lan

Token: vào 242,516 / ra 36,909 qua 213 lần gọi; chi phí ước tính ≈ $0.5492; thời gian 353s.

Ghi chú TC6: hệ thống chỉ gắn cờ `number_check`, không thể phát hiện số sai khi không có audio. TC7: chỉ yêu cầu không có item `confirmed` bịa cho 'phương án đó'.
