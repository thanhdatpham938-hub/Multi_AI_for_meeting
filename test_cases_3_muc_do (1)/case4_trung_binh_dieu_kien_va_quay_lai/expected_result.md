# Case 4 – Trung bình: điều kiện, hoãn và quay lại chủ đề

**Cuộc họp:** chuẩn bị khai trương chi nhánh Thủ Đức của chuỗi cà phê Mộc. 107 câu, dài khoảng 18 phút, liên tục.

**Đặc điểm:** cuộc họp có chương trình rõ, nhưng chỉ **một** người có quyền chốt (Hạnh, COO). Độ khó nằm giữa case 1 và case 2:

- Hai lần đổi phương án A → B có lý do bằng số liệu: khuyến mãi giảm 20% → mua 1 tặng 1; mua máy espresso → thuê.
- Ngày khai trương là quyết định **có điều kiện** (biên bản PCCC), không phải `confirmed`.
- Chủ đề ca tối bị hoãn ở phút 9 rồi **quay lại** ở phút 13 bằng "vụ ca tối lúc nãy", lần này được chốt.
- Người không có quyền (Mai) tự nói "chốt in 5.000 tờ rơi" và bị COO gạt đi.
- Một việc được người khác xung phong nhưng COO giao cho người khác; một việc "ai đó cần…" không có người nhận.
- Có câu đùa ("máy một tỷ, haha") và câu mỉa mai đáp lại ("rồi lấy lương em trả nhé").

**Mục tiêu kiểm tra:** phân biệt đúng `confirmed` / `conditional` / `deferred`, gộp chủ đề quay lại, không gán việc theo người lên tiếng gần nhất.

## Quyết định

| # | Nội dung | Trạng thái đúng | Câu bằng chứng | Lịch sử / bẫy cần tránh | Cờ |
| --- | --- | --- | --- | --- | --- |
| 1 | Khai trương ngày 8/12 | `conditional`, điều kiện: có biên bản nghiệm thu PCCC trước 5/12 | 05:15 (u031) (+ 16:48 tóm lại) | 1/12 `proposed` (Tùng, 04:03) → `superseded` vì PCCC có thể không kịp (Bảo, 04:27–04:37). Câu "1/12 đẹp" của Mai (04:15) chỉ là ý kiến. **Không được `confirmed` 8/12 hay 1/12** | `number_check` |
| 2 | Khuyến mãi khai trương: mua 1 tặng 1 size M trong ba ngày đầu | `confirmed` | 07:14 (u043) | Giảm 20% toàn menu `proposed` (Mai, 06:02) → `superseded`, lý do biên lợi nhuận tuần đầu âm ~3% (06:20–06:33) | |
| 3 | Thuê máy pha espresso sáu tháng, sau sáu tháng đánh giá lại | `confirmed` | 11:44 (u071) | Mua mới ~180 triệu `proposed` (Tùng, 10:28) → `superseded` vì dòng tiền căng (10:38–11:21). Câu đùa 10:46 và câu mỉa mai 10:55 **không** phải quyết định | |
| 4 | Tuyển thêm hai bạn part-time ca tối | `confirmed` | 13:45 (u083) | Lịch sử: "ca tối tính sau" `deferred` (09:16) → `confirmed` (13:45). Hai đoạn 08:47–09:26 và 13:07–13:57 phải **gộp một chủ đề** | |
| 5 | Số lượng tờ rơi in (đề xuất 5.000 tờ) | `deferred` hoặc `open` | 07:44 – 07:59 (u046, u047) | Mai nói "chốt in 5.000 tờ rơi" (07:36) nhưng **không có quyền**; COO nói "Khoan…" rồi yêu cầu xem lại. **Không được `confirmed`** | `authority_unclear` nếu hệ thống bám vào câu 07:36; `number_check` |
| 6 | Thêm bánh mì vào menu buổi sáng | `deferred` | 12:52 (u078) | Chờ COO hỏi công suất bếp trung tâm | |
| 7 | Mời KOL đến khai trương | `deferred` | 15:51 (u096) | Bàn tiếp khi có biên bản PCCC | |
| 8 | Giữ nguyên biển hiệu theo bản đã duyệt | `confirmed` | 14:54 (u090) | Chi tiết phụ, chấp nhận nếu bỏ sót | |
| 9 | Ngân sách marketing khai trương | `open` hoặc `deferred` | 16:27 (u099) | COO "chưa trả lời được". Chấp nhận nếu bỏ sót; **không được bịa con số** | |

**Kiểm tra cốt lõi:** các mục sau **tuyệt đối không được `confirmed`**: "khai trương 1/12", "khai trương 8/12" (chỉ `conditional`), "giảm 20% toàn menu", "mua máy espresso", "in 5.000 tờ rơi", "mua máy một tỷ".

## Việc cần làm

| Nội dung | Người | Hạn | Câu bằng chứng | Bẫy / cờ |
| --- | --- | --- | --- | --- |
| Liên hệ PCCC, hẹn lịch kiểm tra sớm nhất | **Tùng** | Chiều nay | 02:40, 02:57 | Bảo xung phong (02:32) nhưng COO giao cho Tùng. **Không được gán cho Bảo** |
| Kiểm tra lại tải điện trước khi lắp máy | **null** | null | 03:31 | "Ai đó cũng cần…", Tùng chỉ nói phải thuê thợ ngoài, không nhận việc. Cờ `missing_owner` |
| Chuẩn bị kế hoạch quảng cáo theo mốc 8/12, chưa đặt cọc đến khi có biên bản | Mai | null | 05:28, 05:35 | |
| Xem lại số lượng tờ rơi, gửi COO con số hợp lý | Mai | Trong tuần này | 07:59, 08:08 | |
| Gửi lịch đào tạo cho Tùng | Nhi | Thứ Sáu này | 10:03, 10:12 | |
| Đứng lớp buổi đào tạo đầu về quy trình mở/đóng cửa | Tùng | null | 09:54 | Không tự lấy 24/11 làm hạn (ngày đó nằm ở câu khác) |
| Ký hợp đồng thuê máy espresso | Kiệt | Trước 25/11 | 11:55, 12:04 | `number_check` |
| Hỏi bếp trung tâm về công suất làm bánh mì | Hạnh | null | 12:52 | |
| Gửi hợp đồng cho hai bạn part-time ca tối | Nhi | Hôm nay | 13:57 | |
| Đăng ký gói nhạc bản quyền cho chi nhánh | Tùng | null | 15:22, 15:35 | |
| Phỏng vấn tuyển hai vị trí pha chế còn thiếu | Nhi | Cuối tuần (dự kiến) | 08:35 | Chấp nhận nếu ghi là `knowledge` hoặc bỏ sót |

## Các loại khác

| Loại | Nội dung | Câu bằng chứng |
| --- | --- | --- |
| `blocker` | Chưa có biên bản nghiệm thu PCCC nên chưa được mở cửa đón khách; PCCC hẹn tuần sau | 01:46, 02:03 |
| `knowledge` | Đã giải ngân 420 triệu trên dự toán 600 triệu | 01:26 |
| `knowledge` | Nội thất giao ngày 20/11 | 01:05 |
| `knowledge` | Mỗi tuần lùi khai trương mất ~35 triệu tiền thuê mặt bằng | 04:53 |
| `knowledge` | Giảm 20% cả menu → biên lợi nhuận tuần đầu âm ~3%; mua 1 tặng 1 size M → dương ~8% | 06:20, 06:54 |
| `knowledge` | Đã tuyển 6/8 nhân viên, thiếu 2 pha chế; ca tối hiện có 2 người | 08:21, 08:58 |
| `knowledge` | Đào tạo 3 ngày ở chi nhánh Quận 1 từ 24/11 | 09:43 |
| `knowledge` | Mua máy ~180 triệu, thuê ~6 triệu/tháng có bảo trì | 10:28, 10:38 |
| `knowledge` | Hai bạn part-time thêm ~12 triệu/tháng lương, trong định mức | 14:05 |
| `knowledge` | Wifi và máy POS lắp ngày 28/11 | 15:01 |

## Tiêu chí đạt

- Quyết định 1–4 phải có, đúng trạng thái; quyết định 2, 3, 4 có confidence ≥ 0,8 và không có cờ `authority_unclear`.
- Ngày khai trương là `conditional` với điều kiện về biên bản PCCC; 1/12 chỉ xuất hiện trong `history` với `superseded`.
- "Giảm 20%" và "mua máy espresso" chỉ xuất hiện trong `history` với `superseded`.
- Chủ đề ca tối là **một** chủ đề, gộp được 08:47–09:26 và 13:07–13:57.
- Việc liên hệ PCCC gán cho Tùng; việc kiểm tra tải điện có owner `null` và cờ `missing_owner`.
- Ít nhất 8 trên 11 việc cần làm được trích xuất, người và hạn đúng; không bịa hạn cho việc có hạn = null.
- Tỷ lệ chốt nhầm = 0%.

## Điểm hệ thống dễ sai

- Coi câu tóm lại 16:48 "Khai trương 8/12 nếu…" là chốt và bỏ mất vế điều kiện.
- Tin câu "chốt in 5.000 tờ rơi" của Mai vì có từ "chốt".
- Không nối "vụ ca tối lúc nãy" (13:07) về đoạn 08:47, tạo hai mục ca tối mâu thuẫn (một `deferred`, một `confirmed`).
- Gán việc liên hệ PCCC cho Bảo vì Bảo là người xung phong.
- Gán việc kiểm tra tải điện cho Tùng vì Tùng là người trả lời ngay sau.
- Coi "Ừ, rồi lấy lương em trả nhé" là đồng ý mua máy một tỷ.
