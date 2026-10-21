# Chấm lại offline – 2026-10-21 16:34

Không gọi API; khớp mục chỉ theo evidence (không dùng LLM so khớp). Các run cũ chưa có nhãn mới nên chỉ số mới ở mức 0% hoặc `không áp dụng` là đúng thực tế.

## Bộ ngắn (tests/fixtures)

Chỉ số tổng hợp trên các ca không phải giới hạn đã biết (số lần chạy mỗi ca: 3):

| Chỉ số | Giá trị | Ngưỡng | Đạt |
| --- | --- | --- | --- |
| Tỷ lệ chốt nhầm | 0.0% (n=2) (tham khảo) | ≤ 5.0% | ✅ |
| Recall quyết định | 100.0% (n=5) (tham khảo) | ≥ 85.0% | ✅ |
| Precision việc cần làm | 60.0% (n=5) (tham khảo) | ≥ 80.0% | ❌ |
| Độ chính xác trích dẫn | 100.0% (n=9) (tham khảo) | ≥ 95.0% | ✅ |
| Owner/deadline bịa | 1 (n=9) (tham khảo) | ≤ 0 | ❌ |
| Trạng thái đúng cho mục chưa chốt | 100.0% (n=3) (tham khảo) | ≥ 80.0% | ✅ |
| Đoạn trích kiểm chứng được | không áp dụng (0 mẫu) | ≥ 95.0% | – |
| Owner/deadline có câu nguồn riêng | 0.0% (n=7) (tham khảo) | ≥ 100.0% | ❌ |
| Phạm vi tri thức đúng | không áp dụng (0 mẫu) | ≥ 75.0% | – |
| Quyết định mâu thuẫn không gắn cờ | 0 (n=7) (tham khảo) | ≤ 0 | ✅ |
| Cờ kỳ vọng có mặt (expect_flags_any) | 0.0% (n=1) (tham khảo) | ≥ 100.0% | ❌ |
| Độ ổn định (đổi trạng thái) | 0.0% | ≤ 10.0% | ✅ |

| Ca | Loại | Kết quả |
| --- | --- | --- |
| TC1 | chấm điểm | ✅ đạt |
| TC2 | chấm điểm | ❌ 1 lỗi |
| TC3 | chấm điểm | ❌ 2 lỗi |
| TC4 | chấm điểm | ✅ đạt |
| TC5 | chấm điểm | ❌ 1 lỗi |
| TC6 | giới hạn đã biết | ✅ đạt |
| TC7 | giới hạn đã biết | ❌ 2 lỗi |

**TC2**
- Bỏ sót action: "Xem lại phần test tải"

**TC3**
- Action thừa: [a01] "Nam hỗ trợ phỏng vấn vòng kỹ thuật nếu cần" owner=Nam
- Action thừa: [a02] "Khởi động lại server staging" owner=Minh

**TC5**
- deadline bịa: "Tuần sau chốt dùng React cho front-end" deadline='tuần sau'

**TC7**
- Action thừa: [a02] "Báo bên toà nhà về máy lạnh hỏng" owner=Lan
- Không có mục nào mang cờ nào trong ['unresolved_reference']

## Bộ dài (test_cases_3_muc_do)

Chỉ số tổng hợp trên các ca không phải giới hạn đã biết (số lần chạy mỗi ca: 1):

| Chỉ số | Giá trị | Ngưỡng | Đạt |
| --- | --- | --- | --- |
| Tỷ lệ chốt nhầm | 60.0% (n=5) (tham khảo) | ≤ 5.0% | ❌ |
| Recall quyết định | 80.0% (n=10) | ≥ 85.0% | ❌ |
| Precision việc cần làm | 73.3% (n=15) | ≥ 80.0% | ❌ |
| Độ chính xác trích dẫn | 100.0% (n=20) | ≥ 95.0% | ✅ |
| Owner/deadline bịa | 1 (n=20) | ≤ 0 | ❌ |
| Trạng thái đúng cho mục chưa chốt | 66.7% (n=3) (tham khảo) | ≥ 80.0% | ❌ |
| Đoạn trích kiểm chứng được | không áp dụng (0 mẫu) | ≥ 95.0% | – |
| Owner/deadline có câu nguồn riêng | 0.0% (n=19) | ≥ 100.0% | ❌ |
| Phạm vi tri thức đúng | không áp dụng (0 mẫu) | ≥ 75.0% | – |
| Quyết định mâu thuẫn không gắn cờ | 6 (n=19) | ≤ 0 | ❌ |
| Cờ kỳ vọng có mặt (expect_flags_any) | không áp dụng (0 mẫu) | ≥ 100.0% | – |
| Độ ổn định | (chạy với `--repeat 3`) | ≤ 10% | – |

| Ca | Loại | Kết quả |
| --- | --- | --- |
| CASE2 | chấm điểm | ❌ 32 lỗi |

**CASE2**
- Chốt nhầm: [d05] "Logo mới duyệt bản màu xanh lá" evidence=['u060']
- Chốt nhầm: [d11] "Làm trang đích đơn giản" evidence=['u092']
- Chốt nhầm: [d17] "Quay series ngoài đường cho chân thật, Ngọc tự cân đối" evidence=['u118']
- Lịch sử thiếu "Chỉ chạy TikTok" superseded trong "Kênh quảng cáo số: chạy cả TikTok và Facebook, TikTok 70% / Facebook 30%"
- Lịch sử thiếu "Chạy Facebook trước" superseded trong "Kênh quảng cáo số: chạy cả TikTok và Facebook, TikTok 70% / Facebook 30%"
- Bỏ sót decision: "Thuê freelancer dựng video, chi phí lấy từ ngân sách quảng cáo số"
- Sai trạng thái "Làm trang đích đơn giản có nút tìm đại lý (hỏi IT trước, bận thì thuê ngoài)": conditional, đáp án ['confirmed']
- Sai trạng thái "Content ưu tiên vị ô long": open, đáp án ['confirmed', 'proposed']
- Bỏ sót decision: "Làm thêm biển quảng cáo ngoài trời (OOH) 200 triệu"
- Thiếu cờ number_check ở "Giá bán lẻ 28 nghìn/chai"
- Sai trạng thái "Ngày ra mắt 5/12": deferred, đáp án ['open', 'proposed']
- Thiếu cờ no_closing_signal ở "Ngày ra mắt 5/12"
- Sai trạng thái "Sự kiện ra mắt mời báo chí 50 người": open, đáp án ['deferred']
- Sai trạng thái "Không làm khảo sát vị trước ra mắt": open, đáp án ['confirmed']
- Sai owner "Khoa gửi đề xuất OOH chi tiết (vị trí, báo giá) cho Bình": 'Bình', đáp án 'Khoa'
- Sai deadline "Khoa gửi đề xuất OOH chi tiết (vị trí, báo giá) cho Bình": None, đáp án 'tuần này'
- Bỏ sót action: "Bình trình đề xuất OOH lên giám đốc tài chính"
- owner bịa: "Tuấn hỗ trợ viết brief gửi agency quay video nếu cần" owner='Tuấn'
- Thiếu cờ missing_owner ở "Viết brief gửi agency quay video (chưa có người nhận, không gán cho Tuấn)"
- Sai owner "Hà đề xuất chương trình khuyến mãi cho đại lý, gửi Phương duyệt": None, đáp án 'Hà'
- Sai deadline "Hà đề xuất chương trình khuyến mãi cho đại lý, gửi Phương duyệt": None, đáp án 'đầu tuần sau'
- Bỏ sót action: "Ngọc làm bài đăng giới thiệu ba vị, chạy trước ra mắt 1 tuần"
- Bỏ sót blocker: "OOH vượt ngân sách, Finance không duyệt được, phải lên giám đốc tài chính"
- Bỏ sót request: "Ngọc cần thêm một người dựng video nếu chạy cả hai kênh"
- Bỏ sót knowledge: "Ngân sách đã duyệt 500 triệu (chưa gồm in bao bì); phân bổ tạm: quảng cáo số 250, KOL 100, sampling 80"
- Bỏ sót knowledge: "Đối thủ chạy TikTok tháng trước 3 triệu lượt xem, Facebook 400 nghìn; đơn qua mã giảm giá từ TikTok gấp đôi"
- Action thừa: [a09] "Ngọc đưa hướng dẫn thiết kế có màu xanh lá" owner=Ngọc
- Action thừa: [a11] "Hà gửi đề xuất chương trình khuyến mãi cho đại lý cho Phương" owner=Hà
- Action thừa: [a04] "Khoa gửi đề xuất chi tiết biển quảng cáo trong tuần này" owner=Khoa
- Action thừa: [a14] "Thuê freelancer dựng video, chi phí lấy từ phần quảng cáo số" owner=Phương
- Các câu ['u030', 'u034', 'u131', 'u132'] không cùng một chủ đề (topics=['t02', 't08'])
- Ca này không được có quyết định mâu thuẫn chưa gắn cờ (6 cặp)

Ghi chú (không tính là lỗi):
- CASE2: Mâu thuẫn không gắn cờ: [d03] "Phân bổ ngân sách tạm: quảng cáo số 250 triệu, KOL 100 triệu, sampling 80 triệu, còn lại dự phòng" vs [d18] "Phân bổ ngân sách quảng cáo: TikTok 70%, Facebook 30%"
- CASE2: Mâu thuẫn không gắn cờ: [d06] "Làm series 'một ngày với TeaGo', Ngọc lên kịch bản gửi Phương tuần sau" vs [d17] "Quay series ngoài đường cho chân thật, Ngọc tự cân đối"
- CASE2: Mâu thuẫn không gắn cờ: [d10] "Mọi bài đều có màu xanh lá của logo để nhận diện" vs [d05] "Logo mới duyệt bản màu xanh lá"
- CASE2: Mâu thuẫn không gắn cờ: [d12] "Hỏi IT dựng trang đích trước, nếu họ bận thì thuê ngoài" vs [d11] "Làm trang đích đơn giản"
- CASE2: Mâu thuẫn không gắn cờ: [d18] "Phân bổ ngân sách quảng cáo: TikTok 70%, Facebook 30%" vs [d14] "Chưa cần làm biển quảng cáo ngoài trời, để sau khi có ngày ra mắt rồi bàn"
- CASE2: Mâu thuẫn không gắn cờ: [d19] "Sampling tại Coopmart thay vì Big C do phí Big C cao gấp đôi" vs [d02] "Chưa quyết định làm sampling trải nghiệm sản phẩm ở siêu thị, chờ Hà hỏi giá phí mặt bằng"

## Tổng (ngắn + dài)

Chỉ số tổng hợp trên các ca không phải giới hạn đã biết (số lần chạy mỗi ca: 3):

| Chỉ số | Giá trị | Ngưỡng | Đạt |
| --- | --- | --- | --- |
| Tỷ lệ chốt nhầm | 42.9% (n=7) (tham khảo) | ≤ 5.0% | ❌ |
| Recall quyết định | 86.7% (n=15) | ≥ 85.0% | ✅ |
| Precision việc cần làm | 70.0% (n=20) | ≥ 80.0% | ❌ |
| Độ chính xác trích dẫn | 100.0% (n=29) | ≥ 95.0% | ✅ |
| Owner/deadline bịa | 2 (n=29) | ≤ 0 | ❌ |
| Trạng thái đúng cho mục chưa chốt | 83.3% (n=6) (tham khảo) | ≥ 80.0% | ✅ |
| Đoạn trích kiểm chứng được | không áp dụng (0 mẫu) | ≥ 95.0% | – |
| Owner/deadline có câu nguồn riêng | 0.0% (n=26) | ≥ 100.0% | ❌ |
| Phạm vi tri thức đúng | không áp dụng (0 mẫu) | ≥ 75.0% | – |
| Quyết định mâu thuẫn không gắn cờ | 6 (n=26) | ≤ 0 | ❌ |
| Cờ kỳ vọng có mặt (expect_flags_any) | 0.0% (n=1) (tham khảo) | ≥ 100.0% | ❌ |
| Độ ổn định (đổi trạng thái) | 0.0% | ≤ 10.0% | ✅ |

| Ca | Loại | Kết quả |
| --- | --- | --- |
| TC1 | chấm điểm | ✅ đạt |
| TC2 | chấm điểm | ❌ 1 lỗi |
| TC3 | chấm điểm | ❌ 2 lỗi |
| TC4 | chấm điểm | ✅ đạt |
| TC5 | chấm điểm | ❌ 1 lỗi |
| TC6 | giới hạn đã biết | ✅ đạt |
| TC7 | giới hạn đã biết | ❌ 2 lỗi |
| CASE2 | chấm điểm | ❌ 32 lỗi |

**TC2**
- Bỏ sót action: "Xem lại phần test tải"

**TC3**
- Action thừa: [a01] "Nam hỗ trợ phỏng vấn vòng kỹ thuật nếu cần" owner=Nam
- Action thừa: [a02] "Khởi động lại server staging" owner=Minh

**TC5**
- deadline bịa: "Tuần sau chốt dùng React cho front-end" deadline='tuần sau'

**TC7**
- Action thừa: [a02] "Báo bên toà nhà về máy lạnh hỏng" owner=Lan
- Không có mục nào mang cờ nào trong ['unresolved_reference']

**CASE2**
- Chốt nhầm: [d05] "Logo mới duyệt bản màu xanh lá" evidence=['u060']
- Chốt nhầm: [d11] "Làm trang đích đơn giản" evidence=['u092']
- Chốt nhầm: [d17] "Quay series ngoài đường cho chân thật, Ngọc tự cân đối" evidence=['u118']
- Lịch sử thiếu "Chỉ chạy TikTok" superseded trong "Kênh quảng cáo số: chạy cả TikTok và Facebook, TikTok 70% / Facebook 30%"
- Lịch sử thiếu "Chạy Facebook trước" superseded trong "Kênh quảng cáo số: chạy cả TikTok và Facebook, TikTok 70% / Facebook 30%"
- Bỏ sót decision: "Thuê freelancer dựng video, chi phí lấy từ ngân sách quảng cáo số"
- Sai trạng thái "Làm trang đích đơn giản có nút tìm đại lý (hỏi IT trước, bận thì thuê ngoài)": conditional, đáp án ['confirmed']
- Sai trạng thái "Content ưu tiên vị ô long": open, đáp án ['confirmed', 'proposed']
- Bỏ sót decision: "Làm thêm biển quảng cáo ngoài trời (OOH) 200 triệu"
- Thiếu cờ number_check ở "Giá bán lẻ 28 nghìn/chai"
- Sai trạng thái "Ngày ra mắt 5/12": deferred, đáp án ['open', 'proposed']
- Thiếu cờ no_closing_signal ở "Ngày ra mắt 5/12"
- Sai trạng thái "Sự kiện ra mắt mời báo chí 50 người": open, đáp án ['deferred']
- Sai trạng thái "Không làm khảo sát vị trước ra mắt": open, đáp án ['confirmed']
- Sai owner "Khoa gửi đề xuất OOH chi tiết (vị trí, báo giá) cho Bình": 'Bình', đáp án 'Khoa'
- Sai deadline "Khoa gửi đề xuất OOH chi tiết (vị trí, báo giá) cho Bình": None, đáp án 'tuần này'
- Bỏ sót action: "Bình trình đề xuất OOH lên giám đốc tài chính"
- owner bịa: "Tuấn hỗ trợ viết brief gửi agency quay video nếu cần" owner='Tuấn'
- Thiếu cờ missing_owner ở "Viết brief gửi agency quay video (chưa có người nhận, không gán cho Tuấn)"
- Sai owner "Hà đề xuất chương trình khuyến mãi cho đại lý, gửi Phương duyệt": None, đáp án 'Hà'
- Sai deadline "Hà đề xuất chương trình khuyến mãi cho đại lý, gửi Phương duyệt": None, đáp án 'đầu tuần sau'
- Bỏ sót action: "Ngọc làm bài đăng giới thiệu ba vị, chạy trước ra mắt 1 tuần"
- Bỏ sót blocker: "OOH vượt ngân sách, Finance không duyệt được, phải lên giám đốc tài chính"
- Bỏ sót request: "Ngọc cần thêm một người dựng video nếu chạy cả hai kênh"
- Bỏ sót knowledge: "Ngân sách đã duyệt 500 triệu (chưa gồm in bao bì); phân bổ tạm: quảng cáo số 250, KOL 100, sampling 80"
- Bỏ sót knowledge: "Đối thủ chạy TikTok tháng trước 3 triệu lượt xem, Facebook 400 nghìn; đơn qua mã giảm giá từ TikTok gấp đôi"
- Action thừa: [a09] "Ngọc đưa hướng dẫn thiết kế có màu xanh lá" owner=Ngọc
- Action thừa: [a11] "Hà gửi đề xuất chương trình khuyến mãi cho đại lý cho Phương" owner=Hà
- Action thừa: [a04] "Khoa gửi đề xuất chi tiết biển quảng cáo trong tuần này" owner=Khoa
- Action thừa: [a14] "Thuê freelancer dựng video, chi phí lấy từ phần quảng cáo số" owner=Phương
- Các câu ['u030', 'u034', 'u131', 'u132'] không cùng một chủ đề (topics=['t02', 't08'])
- Ca này không được có quyết định mâu thuẫn chưa gắn cờ (6 cặp)

Ghi chú (không tính là lỗi):
- CASE2: Mâu thuẫn không gắn cờ: [d03] "Phân bổ ngân sách tạm: quảng cáo số 250 triệu, KOL 100 triệu, sampling 80 triệu, còn lại dự phòng" vs [d18] "Phân bổ ngân sách quảng cáo: TikTok 70%, Facebook 30%"
- CASE2: Mâu thuẫn không gắn cờ: [d06] "Làm series 'một ngày với TeaGo', Ngọc lên kịch bản gửi Phương tuần sau" vs [d17] "Quay series ngoài đường cho chân thật, Ngọc tự cân đối"
- CASE2: Mâu thuẫn không gắn cờ: [d10] "Mọi bài đều có màu xanh lá của logo để nhận diện" vs [d05] "Logo mới duyệt bản màu xanh lá"
- CASE2: Mâu thuẫn không gắn cờ: [d12] "Hỏi IT dựng trang đích trước, nếu họ bận thì thuê ngoài" vs [d11] "Làm trang đích đơn giản"
- CASE2: Mâu thuẫn không gắn cờ: [d18] "Phân bổ ngân sách quảng cáo: TikTok 70%, Facebook 30%" vs [d14] "Chưa cần làm biển quảng cáo ngoài trời, để sau khi có ngày ra mắt rồi bàn"
- CASE2: Mâu thuẫn không gắn cờ: [d19] "Sampling tại Coopmart thay vì Big C do phí Big C cao gấp đôi" vs [d02] "Chưa quyết định làm sampling trải nghiệm sản phẩm ở siêu thị, chờ Hà hỏi giá phí mặt bằng"

- Chấm lại TC1: 3 run, đáp án tc1.expected.json
- Chấm lại TC2: 3 run, đáp án tc2.expected.json
- Chấm lại TC3: 3 run, đáp án tc3.expected.json
- Chấm lại TC4: 3 run, đáp án tc4.expected.json
- Chấm lại TC5: 3 run, đáp án tc5.expected.json
- Chấm lại TC6: 3 run, đáp án tc6.expected.json
- Chấm lại TC7: 3 run, đáp án tc7.expected.json
- Chấm lại CASE2: 1 run, đáp án expected.json
