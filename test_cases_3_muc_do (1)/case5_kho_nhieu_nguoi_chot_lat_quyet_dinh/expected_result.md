# Case 5 – Khó: nhiều người có quyền chốt, quyết định bị lật lại

**Cuộc họp:** hậu kiểm sự cố cổng thanh toán và kế hoạch Black Friday của sàn ShopNhanh. 113 câu, dài khoảng 19 phút, liên tục.

**Đặc điểm:** có **ba** người có quyền chốt (CEO Hòa, CTO Quân, Head of Product Linh), và CEO vào họp muộn ở phút 10. Bẫy chính:

- CTO nói "**Chốt** rollback về 3.2 tối nay" (04:11), nhưng 1 phút sau tự lật lại sang hotfix khi biết rollback làm mất tính năng voucher khung giờ. Câu có từ "chốt" **không phải kết quả cuối**.
- CTO và Head of Product bất đồng về flash sale (hoãn / 10.000 đơn mỗi giờ). CEO vào sau và quyết phương án thứ ba (5.000 đơn mỗi giờ + hàng đợi). Cả hai phương án trước đều `superseded`.
- Bồi thường voucher: Head of Product chốt **có điều kiện** "nếu tài chính duyệt" (07:18), gần 7 phút sau CEO quay lại bằng "**vụ voucher đó**" (13:45) và duyệt luôn, bỏ điều kiện. Trạng thái cuối là `confirmed`, không phải `conditional`.
- Câu thuật lại ("Hôm trước anh Hòa bảo…"), câu mỉa mai ("…mà sập 47 phút, hay thật"), câu giả định ("Giả sử traffic gấp ba…").
- Việc được người này xung phong nhưng giao cho người khác (postmortem; hàng đợi giao cho **Tú**, người không có mặt trong họp).
- Một câu "ai đó cần gửi email" được giải quyết ngay sau đó, không được thành một việc không có người phụ trách.
- Một vấn đề kết thúc mà không ai kết luận (thông báo cho ngân hàng).

**Mục tiêu kiểm tra:** theo dõi đúng trạng thái cuối khi quyết định bị lật nhiều lần và khi người có quyền cao hơn vào sau; không lấy câu có từ "chốt" đầu tiên làm kết quả.

## Quyết định

| # | Nội dung | Trạng thái đúng | Câu bằng chứng | Lịch sử / bẫy cần tránh | Cờ |
| --- | --- | --- | --- | --- | --- |
| 1 | Khắc phục bằng hotfix: tăng pool kết nối và giới hạn worker, **không** rollback | `confirmed` | 05:12 (u031) (+ 17:24 tóm lại) | Rollback 3.2 `proposed` (Thảo, 03:39) → `confirmed` bởi CTO (04:11) → `superseded` (04:29–05:12), lý do: rollback làm mất tính năng voucher khung giờ cho Black Friday. **Không được có mục "rollback" ở trạng thái `confirmed`** | |
| 2 | Flash sale Black Friday 0 giờ vẫn chạy, giới hạn 5.000 đơn mỗi giờ, bắt buộc có hàng đợi ở trang thanh toán | `confirmed` | 11:33, 11:47 (u068, u069) (+ 17:44) | 10.000 đơn/giờ `proposed` (Linh, 08:39) và "hoãn flash sale 0 giờ" `proposed` (Quân, 08:50) → cả hai `superseded` bởi quyết định của CEO. Người chốt là CEO | `number_check` |
| 3 | Tặng voucher 50 nghìn cho mọi đơn lỗi tối qua, không cần chờ tài chính | `confirmed` | 13:45 (u083) | My đề xuất (06:56) → `conditional` "nếu tài chính duyệt" (Linh, 07:18) → `confirmed` không điều kiện bởi CEO (13:45). "Vụ voucher đó" phải nối về đoạn 06:46–07:42, **một** chủ đề. Trạng thái cuối **không phải** `conditional` | `number_check` |
| 4 | Đóng băng deploy từ 25/11 đến hết 30/11, chỉ cho phép hotfix khẩn cấp | `confirmed` | 16:30 (u099) (+ 15:57) | CTO nêu ý muốn (15:57), CEO xác nhận (16:30) | `number_check` |
| 5 | Tăng gấp đôi số server tuần Black Friday (~80 triệu) | `deferred` | 13:10 (u079) | Chờ kết quả load test thứ Tư. Câu "Giả sử traffic gấp ba…" (09:27) là giả định, **không** phải quyết định | `number_check` |
| 6 | Có thông báo sự cố cho đối tác ngân hàng không | `open` | 14:46 – 15:34 (u089–u094) | "Hay là báo luôn cho chắc?" là gợi ý; CEO nói "chưa kết luận được". Chấp nhận ghi là `open_issue` | `no_closing_signal` |
| 7 | Làm trang trạng thái hệ thống công khai | `deferred` | 17:07 (u103) | Bàn tiếp sau Black Friday | |

**Không phải quyết định:** "Hôm trước anh Hòa bảo không được để khách chịu thiệt" (07:33, câu thuật lại); "sập 47 phút, hay thật" (03:20, mỉa mai); "Giả sử traffic gấp ba…" (09:27).

**Kiểm tra cốt lõi:** các mục sau **tuyệt đối không được `confirmed`**: "rollback về 3.2", "flash sale 10.000 đơn mỗi giờ", "hoãn flash sale 0 giờ", "tăng gấp đôi server", "thông báo cho ngân hàng". Voucher **không được** để `conditional` ở trạng thái cuối.

## Việc cần làm

| Nội dung | Người | Hạn | Câu bằng chứng | Bẫy / cờ |
| --- | --- | --- | --- | --- |
| Hotfix pool kết nối và giới hạn worker, deploy | Phúc | Trước 10 giờ sáng mai | 05:12 | |
| Test hotfix trên staging, có test tải | Duy | Tối nay | 05:32, 05:43 | |
| Chuyển cảnh báo thanh toán sang kênh trực mới, gắn on-call qua điện thoại | Thảo | Hôm nay | 05:52, 06:07 | |
| Viết báo cáo postmortem | **Phúc** | Thứ Sáu này | 06:26, 06:37 | Thảo xung phong (06:16) nhưng CTO giao cho Phúc. **Không được gán cho Thảo** |
| Review phần hạ tầng của postmortem | Thảo | null | 06:26 | |
| Soạn email xin lỗi khách, gắn mã voucher | My | null (Linh duyệt trước 5 giờ chiều nay) | 08:08, 14:09, 14:17 | Câu "ai đó cần gửi email xin lỗi" (07:50) được giải quyết ngay; **không** tạo thêm một việc owner `null` trùng lặp |
| Duyệt email xin lỗi trước khi gửi | Linh | Trước 5 giờ chiều nay | 08:08 | |
| Chạy load test Black Friday, gửi kết quả vào nhóm | Duy | Trước thứ Tư | 09:48, 10:04 | Duy rời họp sớm sau khi nhận việc |
| Làm hàng đợi ở trang thanh toán | **Tú** | Trước 24/11 | 12:29, 12:49 | Phúc nói "em làm được" (12:18) nhưng CTO giao cho Tú (không có mặt). Hạn nằm ở câu khác (12:49) nên evidence phải gồm cả hai câu. `number_check` |
| Review hàng đợi | Phúc | null | 12:29 | |
| Giao việc hàng đợi cho Tú sau họp | Quân | Sau họp | 12:29 | Chấp nhận nếu bỏ sót |
| Báo anh Sơn bên tài chính về khoản 160 triệu voucher | Hòa | null ("sau") | 14:00 | Không tự đặt hạn |
| Gọi điện xin lỗi 214 khách bị trừ tiền mà không có đơn | My (CSKH) | Trong hai ngày tới | 14:24, 14:39 | |

## Các loại khác

| Loại | Nội dung | Câu bằng chứng |
| --- | --- | --- |
| `knowledge` | Sự cố 20:12–20:59 (47 phút), tỷ lệ lỗi đỉnh 38%, ~3.200 đơn thanh toán thất bại | 00:58, 01:11 |
| `knowledge` | CSKH nhận hơn 900 cuộc gọi/tin nhắn; 214 khách bị trừ tiền mà không có đơn, ngân hàng hoàn tự động 3–5 ngày | 01:22, 01:47 |
| `knowledge` | Nguyên nhân gốc: bản 3.3 tăng worker từ 8 lên 24 nhưng pool kết nối giữ 50, cạn kết nối lúc cao điểm | 02:06, 02:20 |
| `knowledge` | Cảnh báo bắn 20:15 vào kênh cũ không ai trực, 20:40 mới phát hiện (mất 25 phút) | 02:30, 02:44 |
| `knowledge` | Bản 3.3 không được test tải | 03:02, 03:11 |
| `knowledge` | Flash sale 0 giờ năm ngoái mang về 30% doanh thu cả ngày | 10:58 |
| `knowledge` | Có hàng đợi thì hệ thống chịu an toàn ~5.000 đơn mỗi giờ | 11:21 |
| `knowledge` | Banner đếm ngược chỉ là frontend, deploy trước 25/11 được | 16:19 |

## Tiêu chí đạt

- Quyết định 1–4 phải có, đúng nội dung, `confirmed`, không có cờ `authority_unclear` (người chốt là CTO hoặc CEO, đều có quyền).
- Rollback, 10.000 đơn/giờ và "hoãn flash sale" chỉ xuất hiện trong `history` với `superseded`.
- Voucher là **một** chủ đề, gộp 06:46–07:42 và 13:26–14:17; trạng thái cuối `confirmed`.
- Postmortem gán cho Phúc, hàng đợi gán cho Tú.
- Ít nhất 9 trên 13 việc cần làm được trích xuất, người và hạn đúng; không bịa hạn cho việc có hạn = null.
- Tỷ lệ chốt nhầm = 0%.

## Điểm hệ thống dễ sai

- Lấy câu 04:11 "Chốt rollback về 3.2" làm quyết định cuối vì có từ "chốt" và người nói là CTO.
- Giữ cả hai mục "rollback" và "hotfix" ở trạng thái `confirmed`.
- Lấy phương án của CTO hoặc Head of Product cho flash sale, bỏ qua quyết định của CEO vào sau.
- Để voucher ở `conditional` vì không nối "vụ voucher đó" (13:45) về câu điều kiện 07:18.
- Coi "Hôm trước anh Hòa bảo…" là quyết định của CEO.
- Gán postmortem cho Thảo, hàng đợi cho Phúc (người xung phong hoặc người lên tiếng gần nhất).
- Tạo việc "gửi email xin lỗi" với owner `null` từ câu 07:50, dù My đã nhận ngay sau đó.
