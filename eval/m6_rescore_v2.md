# Chấm lại offline – 2026-10-22 21:42

> **Ghi chú S2b (22/10):** chấm lại miễn phí (không gọi API) lượt M6 (`eval/results/latest.json`) bằng bộ chấm khớp đã sửa. Chỉ phản ánh việc sửa bộ chấm (d15 trang đích không còn bị tính chốt nhầm); sửa `_merge_retry` chỉ ảnh hưởng lần chạy mới. Case 2 chấm bằng `--answer CASE2=.../expected.json` vì run có tên nguồn `transcript`.

Không gọi API; khớp mục chỉ theo evidence (không dùng LLM so khớp). Các run cũ chưa có nhãn mới nên chỉ số mới ở mức 0% hoặc `không áp dụng` là đúng thực tế.

## Bộ ngắn (tests/fixtures)

Chỉ số tổng hợp trên các ca không phải giới hạn đã biết (số lần chạy mỗi ca: 1):

| Chỉ số | Giá trị | Ngưỡng | Đạt |
| --- | --- | --- | --- |
| Tỷ lệ chốt nhầm | 33.3% (n=3) (tham khảo) | ≤ 5.0% | ❌ |
| Recall quyết định | 100.0% (n=5) (tham khảo) | ≥ 85.0% | ✅ |
| Precision việc cần làm | 66.7% (n=6) (tham khảo) | ≥ 80.0% | ❌ |
| Độ chính xác trích dẫn | 100.0% (n=10) | ≥ 95.0% | ✅ |
| Owner/deadline bịa | 0 (n=10) | ≤ 0 | ✅ |
| Trạng thái đúng cho mục chưa chốt | 100.0% (n=3) (tham khảo) | ≥ 80.0% | ✅ |
| Đoạn trích kiểm chứng được | 100.0% (n=34) | ≥ 95.0% | ✅ |
| Owner/deadline có câu nguồn riêng | 100.0% (n=8) (tham khảo) | ≥ 100.0% | ✅ |
| Phạm vi tri thức đúng | không áp dụng (0 mẫu) | ≥ 75.0% | – |
| Quyết định mâu thuẫn không gắn cờ | 0 (n=9) (tham khảo) | ≤ 0 | ✅ |
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
- Action thừa: [a01] "Lan chuẩn bị số liệu chi phí cho phương án on-premise" owner=Lan

**TC2**
- Chốt nhầm: [d01] "Minh xin nghỉ buổi chiều thứ Năm được chấp thuận" evidence=['u014']

**TC4**
- Action thừa: [a01] "Lan hỏi sếp về ngân sách marketing rồi báo lại" owner=Lan

## Bộ dài (test_cases_3_muc_do)

Chỉ số tổng hợp trên các ca không phải giới hạn đã biết (số lần chạy mỗi ca: 1):

| Chỉ số | Giá trị | Ngưỡng | Đạt |
| --- | --- | --- | --- |
| Tỷ lệ chốt nhầm | 72.7% (n=11) | ≤ 5.0% | ❌ |
| Recall quyết định | 90.0% (n=10) | ≥ 85.0% | ✅ |
| Precision việc cần làm | 58.8% (n=17) | ≥ 80.0% | ❌ |
| Độ chính xác trích dẫn | 100.0% (n=25) | ≥ 95.0% | ✅ |
| Owner/deadline bịa | 0 (n=25) | ≤ 0 | ✅ |
| Trạng thái đúng cho mục chưa chốt | 100.0% (n=4) (tham khảo) | ≥ 80.0% | ✅ |
| Đoạn trích kiểm chứng được | 100.0% (n=67) | ≥ 95.0% | ✅ |
| Owner/deadline có câu nguồn riêng | 100.0% (n=23) | ≥ 100.0% | ✅ |
| Phạm vi tri thức đúng | 60.0% (n=5) (tham khảo) | ≥ 75.0% | ❌ |
| Quyết định mâu thuẫn không gắn cờ | 0 (n=25) | ≤ 0 | ✅ |
| Cờ kỳ vọng có mặt (expect_flags_any) | không áp dụng (0 mẫu) | ≥ 100.0% | – |
| Độ ổn định | (chạy với `--repeat 3`) | ≤ 10% | – |

| Ca | Loại | Kết quả |
| --- | --- | --- |
| CASE2 | chấm điểm | ❌ 30 lỗi |

**CASE2**
- Chốt nhầm: [d02] "Không mời Sơn Tùng vì ngân sách có hạn" evidence=['u029']
- Chốt nhầm: [d07] "Duyệt logo mới bản màu xanh lá" evidence=['u060']
- Chốt nhầm: [d09] "Ngọc tự quyết bài đăng giới thiệu ba vị" evidence=['u068']
- Chốt nhầm: [d10] "Ngọc tự quyết bài đăng giới thiệu ba vị, chạy trước ngày ra mắt một tuần để tạo tò mò" evidence=['u068']
- Chốt nhầm: [d25] "Sampling tại Coopmart thay vì Big C do phí cao gấp đôi" evidence=['u132']
- Chốt nhầm: [d08] "Ngọc lên kịch bản series 'một ngày với TeaGo', tuần sau gửi Phương xem" evidence=['u065']
- Chốt nhầm: [d18] "Sales tự đề xuất chương trình khuyến mãi cho đại lý, gửi Phương duyệt" evidence=['u104']
- Chốt nhầm: [d22] "Quay ngoài đường cho chân thật, Ngọc tự cân đối" evidence=['u118']
- Lịch sử thiếu "Chỉ chạy TikTok" superseded trong "Kênh quảng cáo số: chạy cả TikTok và Facebook, TikTok 70% / Facebook 30%"
- Bỏ sót decision: "Thuê freelancer dựng video, chi phí lấy từ ngân sách quảng cáo số"
- Sai trạng thái "Content ưu tiên vị ô long": open, đáp án ['confirmed', 'proposed']
- Thiếu cờ number_check ở "Giá bán lẻ 28 nghìn/chai"
- Sai trạng thái "Ngày ra mắt 5/12": deferred, đáp án ['open', 'proposed']
- Sai owner "Khoa gửi đề xuất OOH chi tiết (vị trí, báo giá) cho Bình": 'Bình', đáp án 'Khoa'
- Sai deadline "Khoa gửi đề xuất OOH chi tiết (vị trí, báo giá) cho Bình": None, đáp án 'tuần này'
- Bỏ sót action: "Bình trình đề xuất OOH lên giám đốc tài chính"
- Bỏ sót action: "Ngọc lên kịch bản series 'một ngày với TeaGo' (~10 tập)"
- Sai owner "Hà đề xuất chương trình khuyến mãi cho đại lý, gửi Phương duyệt": None, đáp án 'Hà'
- Sai deadline "Hà đề xuất chương trình khuyến mãi cho đại lý, gửi Phương duyệt": None, đáp án 'đầu tuần sau'
- Bỏ sót action: "Ngọc làm bài đăng giới thiệu ba vị, chạy trước ra mắt 1 tuần"
- Bỏ sót request: "Ngọc cần thêm một người dựng video nếu chạy cả hai kênh"
- Action thừa: [a08] "Ngọc lên lịch đăng bài dự kiến" owner=Ngọc
- Action thừa: [a10] "Ngọc đưa màu xanh lá vào hướng dẫn thiết kế" owner=Ngọc
- Action thừa: [a16] "Thuê freelancer, chi phí lấy từ phần ngân sách quảng cáo số" owner=None
- Action thừa: [a04] "Khoa gửi đề xuất chi tiết biển quảng cáo trong tuần này" owner=Khoa
- Action thừa: [a09] "Tuấn xử lý nhạc nền khác cho TikTok" owner=Tuấn
- Action thừa: [a11] "Sales cung cấp danh sách đại lý cho trang đích" owner=Sales
- Action thừa: [a13] "Gửi đề xuất chương trình khuyến mãi cho đại lý cho Phương đầu tuần sau" owner=Hà
- Vi phạm: mời Sơn Tùng là câu đùa, không phải quyết định → [d02] "Không mời Sơn Tùng vì ngân sách có hạn"
- Các câu ['u030', 'u034', 'u131', 'u132'] không cùng một chủ đề (topics=['t02', 't09'])

## Tổng (ngắn + dài)

Chỉ số tổng hợp trên các ca không phải giới hạn đã biết (số lần chạy mỗi ca: 1):

| Chỉ số | Giá trị | Ngưỡng | Đạt |
| --- | --- | --- | --- |
| Tỷ lệ chốt nhầm | 64.3% (n=14) | ≤ 5.0% | ❌ |
| Recall quyết định | 93.3% (n=15) | ≥ 85.0% | ✅ |
| Precision việc cần làm | 60.9% (n=23) | ≥ 80.0% | ❌ |
| Độ chính xác trích dẫn | 100.0% (n=35) | ≥ 95.0% | ✅ |
| Owner/deadline bịa | 0 (n=35) | ≤ 0 | ✅ |
| Trạng thái đúng cho mục chưa chốt | 100.0% (n=7) (tham khảo) | ≥ 80.0% | ✅ |
| Đoạn trích kiểm chứng được | 100.0% (n=101) | ≥ 95.0% | ✅ |
| Owner/deadline có câu nguồn riêng | 100.0% (n=31) | ≥ 100.0% | ✅ |
| Phạm vi tri thức đúng | 60.0% (n=5) (tham khảo) | ≥ 75.0% | ❌ |
| Quyết định mâu thuẫn không gắn cờ | 0 (n=34) | ≤ 0 | ✅ |
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
| CASE2 | chấm điểm | ❌ 30 lỗi |

**TC1**
- Action thừa: [a01] "Lan chuẩn bị số liệu chi phí cho phương án on-premise" owner=Lan

**TC2**
- Chốt nhầm: [d01] "Minh xin nghỉ buổi chiều thứ Năm được chấp thuận" evidence=['u014']

**TC4**
- Action thừa: [a01] "Lan hỏi sếp về ngân sách marketing rồi báo lại" owner=Lan

**CASE2**
- Chốt nhầm: [d02] "Không mời Sơn Tùng vì ngân sách có hạn" evidence=['u029']
- Chốt nhầm: [d07] "Duyệt logo mới bản màu xanh lá" evidence=['u060']
- Chốt nhầm: [d09] "Ngọc tự quyết bài đăng giới thiệu ba vị" evidence=['u068']
- Chốt nhầm: [d10] "Ngọc tự quyết bài đăng giới thiệu ba vị, chạy trước ngày ra mắt một tuần để tạo tò mò" evidence=['u068']
- Chốt nhầm: [d25] "Sampling tại Coopmart thay vì Big C do phí cao gấp đôi" evidence=['u132']
- Chốt nhầm: [d08] "Ngọc lên kịch bản series 'một ngày với TeaGo', tuần sau gửi Phương xem" evidence=['u065']
- Chốt nhầm: [d18] "Sales tự đề xuất chương trình khuyến mãi cho đại lý, gửi Phương duyệt" evidence=['u104']
- Chốt nhầm: [d22] "Quay ngoài đường cho chân thật, Ngọc tự cân đối" evidence=['u118']
- Lịch sử thiếu "Chỉ chạy TikTok" superseded trong "Kênh quảng cáo số: chạy cả TikTok và Facebook, TikTok 70% / Facebook 30%"
- Bỏ sót decision: "Thuê freelancer dựng video, chi phí lấy từ ngân sách quảng cáo số"
- Sai trạng thái "Content ưu tiên vị ô long": open, đáp án ['confirmed', 'proposed']
- Thiếu cờ number_check ở "Giá bán lẻ 28 nghìn/chai"
- Sai trạng thái "Ngày ra mắt 5/12": deferred, đáp án ['open', 'proposed']
- Sai owner "Khoa gửi đề xuất OOH chi tiết (vị trí, báo giá) cho Bình": 'Bình', đáp án 'Khoa'
- Sai deadline "Khoa gửi đề xuất OOH chi tiết (vị trí, báo giá) cho Bình": None, đáp án 'tuần này'
- Bỏ sót action: "Bình trình đề xuất OOH lên giám đốc tài chính"
- Bỏ sót action: "Ngọc lên kịch bản series 'một ngày với TeaGo' (~10 tập)"
- Sai owner "Hà đề xuất chương trình khuyến mãi cho đại lý, gửi Phương duyệt": None, đáp án 'Hà'
- Sai deadline "Hà đề xuất chương trình khuyến mãi cho đại lý, gửi Phương duyệt": None, đáp án 'đầu tuần sau'
- Bỏ sót action: "Ngọc làm bài đăng giới thiệu ba vị, chạy trước ra mắt 1 tuần"
- Bỏ sót request: "Ngọc cần thêm một người dựng video nếu chạy cả hai kênh"
- Action thừa: [a08] "Ngọc lên lịch đăng bài dự kiến" owner=Ngọc
- Action thừa: [a10] "Ngọc đưa màu xanh lá vào hướng dẫn thiết kế" owner=Ngọc
- Action thừa: [a16] "Thuê freelancer, chi phí lấy từ phần ngân sách quảng cáo số" owner=None
- Action thừa: [a04] "Khoa gửi đề xuất chi tiết biển quảng cáo trong tuần này" owner=Khoa
- Action thừa: [a09] "Tuấn xử lý nhạc nền khác cho TikTok" owner=Tuấn
- Action thừa: [a11] "Sales cung cấp danh sách đại lý cho trang đích" owner=Sales
- Action thừa: [a13] "Gửi đề xuất chương trình khuyến mãi cho đại lý cho Phương đầu tuần sau" owner=Hà
- Vi phạm: mời Sơn Tùng là câu đùa, không phải quyết định → [d02] "Không mời Sơn Tùng vì ngân sách có hạn"
- Các câu ['u030', 'u034', 'u131', 'u132'] không cùng một chủ đề (topics=['t02', 't09'])

- Chấm lại TC1: 1 run, đáp án tc1.expected.json
- Chấm lại TC2: 1 run, đáp án tc2.expected.json
- Chấm lại TC3: 1 run, đáp án tc3.expected.json
- Chấm lại TC4: 1 run, đáp án tc4.expected.json
- Chấm lại TC5: 1 run, đáp án tc5.expected.json
- Chấm lại TC6: 1 run, đáp án tc6.expected.json
- Chấm lại TC7: 1 run, đáp án tc7.expected.json
- Chấm lại CASE2: 1 run, đáp án expected.json
