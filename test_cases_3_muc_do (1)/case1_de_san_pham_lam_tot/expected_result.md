# Case 1 – Dễ: sản phẩm dự kiến làm tốt

**Cuộc họp:** Sprint planning Sprint 7, app đặt lịch spa BeautyBook. 102 câu, dài khoảng 22 phút, liên tục.

**Đặc điểm:** cuộc họp có cấu trúc rõ, đi theo chương trình. Người chốt là PO và Tech Lead, cả hai đều có quyền chốt và dùng tín hiệu chốt rõ ("chốt…", "Ok, …"). Việc cần làm phần lớn có người và hạn cụ thể. Có một lần đổi phương án A → B (MoMo → VNPay) kèm lý do. Cuối buổi có hai câu tóm lại khớp với các quyết định.

**Mục tiêu kiểm tra:** luồng cơ bản chạy đúng; trích xuất đủ và chính xác; xử lý được A → B đơn giản.

## Quyết định (đều `confirmed`)

| # | Nội dung | Câu bằng chứng | Lịch sử / ghi chú | Cờ |
| --- | --- | --- | --- | --- |
| 1 | Phạm vi Sprint 7: đặt lịch lặp lại + thanh toán online | 07:37 (+ 20:35) | — | |
| 2 | Tích điểm thành viên dời sang Sprint 8 | 07:37 (+ 07:25) | Có thể gộp vào quyết định 1 hoặc tách riêng, đều đạt | |
| 3 | Cổng thanh toán: VNPay | 10:29 | MoMo `proposed` (08:18) → `superseded` (09:15–09:49), lý do: khách đã có hợp đồng VNPay, phí thấp, đối soát chung | |
| 4 | Code freeze 26/10, phát hành 28/10 lúc 22:00 | 14:41, 15:06 | 13:15 PO đề xuất 28/10; 14:06 Tech Lead đề xuất lịch freeze; 14:41 PO chốt | `number_check` |
| 5 | Thanh toán từng buổi, mỗi buổi trước 24 giờ (không thanh toán cả chuỗi) | 19:29 | Phương án "cả chuỗi" được nêu ở 18:34 và bị loại | `number_check` |
| 6 | Sprint 7 chưa làm hoàn tiền tự động, lễ tân hoàn tay | 12:37 | | |
| 7 | Lỗi múi giờ để trong backlog, chưa đưa vào Sprint 7 | 03:46 | Vy đề xuất đưa vào sprint (03:29), PO không đồng ý | |
| 8 | Job sinh lịch giới hạn 8 tuần tới | 05:15 | Tech Lead quyết, Hải đồng ý. Chấp nhận nếu hệ thống ghi là `knowledge` hoặc `decision` | |
| 9 | Màn hình thanh toán hiển thị đồng hồ đếm ngược | 11:59 | Chấp nhận nếu bỏ sót (chi tiết nhỏ) | |

**Không được** xuất hiện MoMo hay "thanh toán cả chuỗi" là quyết định đã chốt.

## Việc cần làm

| Nội dung | Người | Hạn | Câu bằng chứng | Cờ |
| --- | --- | --- | --- | --- |
| Test tính năng thông báo đẩy trên môi trường test | Long | Sáng nay | 02:13 | |
| Test lại lỗi đặt trùng lịch | Long | Hôm nay | 03:09 | |
| Liên hệ khách xin tài khoản sandbox VNPay, gửi Hải | Trang | Thứ Năm 16/10 | 10:56 | `number_check` |
| Làm API thanh toán VNPay | Hải | 22/10 | 15:33 | `number_check` |
| Làm job sinh lịch lặp lại | Đức | 21/10 | 16:07, 16:18 | `number_check` |
| Làm màn hình đặt lịch lặp lại và màn hình thanh toán | Vy | 24/10 | 16:23 | `number_check` |
| Viết test plan và test case cho hai tính năng | Long | 23/10 | 16:43 | `number_check` |
| Trực phát hành tối 28/10 | Đức | 28/10, 22:00 | 15:06, 15:20 | `number_check` |
| Review code hằng ngày lúc 16:00 | Đức | null (việc lặp lại) | 17:08 | |
| Nhận hai máy Android ở phòng hành chính | Long | null | 17:44 | |
| Chuyển thiết kế màn hình thanh toán vào nhóm chat | Trang | Ngay sau họp | 18:17 | |
| Thêm thông báo nhắc thanh toán trước 24 giờ | Hải | null | 19:41, 19:56 | |

**Bẫy nhỏ:** ở 15:46 Hải đề nghị làm job sinh lịch, nhưng Tech Lead nhận lại (15:57). Việc này **phải gán cho Đức**, không phải Hải.

## Các loại khác

| Loại | Nội dung | Câu bằng chứng |
| --- | --- | --- |
| `blocker` | Chưa có tài khoản sandbox VNPay nên chưa test được | 10:41 |
| `knowledge` | Sprint 6 hoàn thành 34/38 story point; thông báo đẩy trễ do chờ chứng chỉ Apple | 01:08 |
| `knowledge` | Giao dịch sandbox VNPay tự hết hạn sau 15 phút nếu không xác nhận | 11:24 |
| `knowledge` | Năng lực team: 1 sprint 2 tuần làm kịp 2 tính năng; thanh toán ~8 ngày công backend, FE 4 + 3 ngày, QA 2 ngày/tính năng | 06:10 – 06:53 |
| `knowledge` | VNPay hỗ trợ QR và thẻ ATM nội địa | 10:15 |

## Tiêu chí đạt

- Quyết định 1–5 phải có, đúng nội dung, `confirmed`, confidence ≥ 0,8, không có cờ `authority_unclear`.
- MoMo chỉ xuất hiện trong `history` với trạng thái `superseded`.
- Ít nhất 8 trên 12 việc cần làm được trích xuất, người và hạn đúng; việc job sinh lịch gán cho Đức.
- Không bịa hạn cho các việc có hạn = null.
- Tỷ lệ chốt nhầm = 0%.
