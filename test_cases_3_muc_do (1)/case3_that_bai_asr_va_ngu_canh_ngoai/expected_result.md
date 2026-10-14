# Case 3 – Rất khó: sản phẩm dự kiến xử lý chưa tốt / thất bại

**Cuộc họp:** đàm phán hợp đồng CRM với nhà cung cấp. 110 câu, dài khoảng 20 phút, liên tục.

**Đặc điểm:** transcript lấy thẳng từ ASR, chưa qua chỉnh sửa. Bộ thông tin cuộc họp gần như trống (không có chương trình họp, không có người tham dự). Các vấn đề:

- Người nói chỉ có nhãn "Speaker N", và có chỗ ASR gán nhầm người nói.
- Có chỗ mất chữ (`[không nghe rõ]`) và nói chồng (`[nói chồng]`).
- Số tiền bị nghe sai.
- Từ tiếng Anh bị phiên âm: "on bốt", "mai gờ rết", "đét lai".
- Có quyết định dựa vào nội dung **nằm ngoài transcript**: email hôm qua, cuộc họp thứ Hai, một cái gật đầu không được ghi lại, ý kiến của người vắng mặt (anh Tâm).

**Mục tiêu kiểm tra:** ghi nhận giới hạn của hệ thống. Ở đây "đạt" nghĩa là hệ thống **không bịa và biết gắn cờ**, chứ không phải lấy đúng mọi quyết định.

## Sự thật của cuộc họp (con người biết, transcript không thể hiện đủ)

| Sự thật | Transcript ghi | Vì sao hệ thống không thể biết |
| --- | --- | --- |
| Speaker 1 là anh Quang, trưởng phòng IT bên mua, người có quyền chốt. Speaker 3 là chị Thu, kế toán bên mua, được ủy quyền phần thanh toán. Speaker 2 là Vân (kinh doanh), Speaker 4 là Kiên (kỹ thuật) bên bán | Chỉ "Speaker 1–4". Tên Vân, Kiên có xuất hiện trong lời giới thiệu (00:50), tên bên mua thì không | Không có danh sách người dự; ánh xạ "Vân = Speaker 2" phải tự suy luận |
| Giá gói Business là **350 triệu**/năm | "35 triệu" (01:53) | Lỗi ASR, không có audio để nghe lại |
| "Phương án trong email hôm qua" là gói Enterprise tối đa 120 người dùng, giá **450 triệu**/năm | Không có nội dung; giá tính theo đầu người bị mất (03:20, 03:25) | Thông tin nằm trong email, ngoài cuộc họp |
| Sau giảm 10%, giá chốt là **405 triệu**/năm | "bốn linh năm" (12:24) | Không rõ đơn vị, không biết là giá của gói nào |
| Ở 13:07, anh Quang **gật đầu** đồng ý ký trong tuần | Không có câu trả lời của bên mua; Speaker 2 tự nói tiếp (13:19) | Cử chỉ không có trong transcript |
| Câu 06:21 "Bên anh gửi được…" và 07:39 "Được, bên anh gửi file trước ngày 3" thực ra do **anh Quang (Speaker 1)** nói | Gán cho Speaker 3 (người xưng "chị" ở các câu khác) | Lỗi tách người nói của ASR |
| Câu 09:55 "Thôi được rồi, làm luôn đi" là chị Thu **đồng ý** phương án 1 buổi trực tiếp + 1 buổi online, anh Quang không phản đối | Không rõ đồng ý thật hay nói cho xong | Giọng điệu không có trong văn bản |
| Hạn gửi dữ liệu là **3/11**, hạn migrate xong 30/11 | "ngày 3", "[nói chồng] dạ tháng 11 ạ hoặc [không nghe rõ]" | Mất chữ ở đúng câu xác nhận |
| Hạn báo về tích hợp tổng đài là **10/11** | "trước ngày 10" | Không có tháng |
| Gói hỗ trợ mở rộng giá **60 triệu**/năm | "[không nghe rõ] mươi triệu" | Mất chữ |

## Kết quả dự kiến của hệ thống và đánh giá

| Nội dung | Hệ thống nhiều khả năng ra | Kết quả đúng | Đánh giá |
| --- | --- | --- | --- |
| Chọn gói theo phương án email (03:46 – 04:05) | Decision `confirmed` hoặc `open` với nội dung mơ hồ "theo phương án trong email" | Gói Enterprise 120 người dùng, 450 triệu | **Thất bại một phần:** không lấy được nội dung. Chấp nhận nếu **không bịa** tên gói hay giá, và có cờ `authority_unclear` |
| Giá sau giảm (12:24 – 12:36) | Decision giá "bốn linh năm" hoặc tự diễn giải sai thành "45 triệu" | 405 triệu/năm | **Thất bại:** không xác định được con số. Tối thiểu phải có cờ `number_check`; **không được** tự quy đổi thành một con số cụ thể |
| Giá gói Business "35 triệu" (01:53) | `knowledge` với số sai | 350 triệu | **Thất bại:** số sai, cần `number_check` |
| Ký hợp đồng trong tuần (13:07 – 13:19) | Không `confirmed`, hoặc tệ hơn là `confirmed` dựa trên câu của bên bán | `confirmed` (bằng cái gật đầu) | **Thất bại có chấp nhận:** bỏ sót vì cử chỉ không có trong transcript. **Không được** `confirmed` chỉ dựa trên lời bên bán tự nói |
| Gửi file dữ liệu trước ngày 3 (07:39) | Action, owner = "Speaker 3" | Owner là anh Quang (Speaker 1), hạn 3/11 | **Thất bại:** gán sai người do ASR. Deadline phải giữ nguyên "ngày 3", không tự thêm tháng |
| Bên bán migrate xong trước 30/11 (07:01) | Action của bên bán, hạn 30/11 | Đúng | Có thể đạt |
| Chuyển 2 năm dữ liệu gần nhất, 3 năm còn lại lưu trữ (08:20 – 09:04) | Decision `confirmed` + `authority_unclear` | `confirmed` | Có thể đạt |
| Đào tạo: 1 buổi trực tiếp + 1 buổi online (09:47 – 10:04) | `proposed` hoặc `open` | `confirmed` | **Thất bại có chấp nhận:** "Thôi được rồi, làm luôn đi" không đủ rõ; để `open` là hành vi an toàn đúng thiết kế |
| Server ở Singapore hay Việt Nam (05:03 – 06:02) | `deferred`, chờ pháp chế | `deferred` | Có thể đạt; action: Speaker 1 hỏi pháp chế |
| Gói hỗ trợ mở rộng ngoài giờ (11:01 – 11:39) | `deferred` | `deferred`, giá 60 triệu | Đạt nếu không bịa giá |
| Thanh toán hai đợt 50/50 (12:42 – 12:58) | `confirmed` hoặc `proposed` | `confirmed` | Chấp nhận cả hai; phải có `authority_unclear` |
| Module tổng đài (13:42 – 14:53) | `deferred`, chờ hỏi anh Tâm | `deferred`; action báo trước ngày 10 | Có thể đạt. Không được tự thêm tháng cho "ngày 10" |
| Thời hạn hợp đồng hai năm (15:02 – 15:54) | `open` hoặc `deferred` | `deferred` (bên bán hỏi sếp) | Đạt nếu **không** `confirmed` "hai năm" |
| Ký thỏa thuận bảo mật trước khi gửi dữ liệu (06:21 – 06:36) | Request + action bên bán gửi mẫu | Đúng | Có thể đạt |
| Bên bán gửi email tổng hợp sau họp (18:46) | Action, owner Speaker 2 (hoặc "Vân") | Đúng | Có thể đạt |

## Tiêu chí "đạt tối thiểu" cho case này

- Không có quyết định `confirmed` nào có nội dung **bịa thêm** so với transcript (ví dụ tự ghi "gói Enterprise", "405 triệu", "3/11", "10/11").
- Mọi decision đều có cờ `authority_unclear` vì người nói chỉ là "Speaker N".
- Mọi mục có số tiền hoặc ngày có cờ `number_check`.
- Các mục lấy bằng chứng từ câu chứa `[không nghe rõ]` hoặc `[nói chồng]` có độ tin cậy thấp (< 0,7).
- Không `confirmed` việc ký hợp đồng chỉ dựa trên câu của bên bán.
- Không `confirmed` thời hạn hợp đồng hai năm.

## Vì sao đây là thất bại "đúng thiết kế"

Hệ thống MVP chỉ đọc văn bản. Nó không có audio, không có kho tri thức các cuộc họp trước, và không đọc email. Thông tin quan trọng của cuộc họp này lại nằm đúng ở những chỗ đó. Kết quả mong muốn là hệ thống **biết mình không chắc** và đẩy mọi mục lên đầu danh sách duyệt, để con người sửa trong vài phút.

**Hướng khắc phục sau MVP:**
- Nhận audio và gắn đoạn ghi âm vào mục có cờ.
- Bắt buộc nhập danh sách người dự để gán tên cho Speaker.
- Liên kết kết quả đã duyệt của cuộc họp trước.
- Cho phép đính kèm email hoặc tài liệu liên quan làm bối cảnh.
