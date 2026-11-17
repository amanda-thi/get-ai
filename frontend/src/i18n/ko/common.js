// Terjemahan Korea untuk teks yang dipakai bersama di banyak halaman
// (navigasi, login, tombol umum, status States, dan semua label dari lib/format.js).
//
// Kunci = teks sumber Bahasa Indonesia/Inggris apa adanya (harus sama persis).
// Nilai = terjemahan Korea.
export default {
  // --- Navigasi & Layout ---
  Dashboard: '대시보드',
  'Tender Monitoring': '입찰 모니터링',
  'Company Leads': '기업 리드',
  'Marketing Outreach': '마케팅 아웃리치',
  Reports: '리포트',
  'Automation Settings': '자동화 설정',
  Modul: '모듈',
  'Buka menu': '메뉴 열기',
  Keluar: '로그아웃',
  'Ganti bahasa': '언어 변경',
  'Logo PT Green Eco Teknologi': 'PT Green Eco Teknologi 로고',

  // --- Login ---
  'Business Automation': '비즈니스 자동화',
  Email: '이메일',
  Password: '비밀번호',
  Masuk: '로그인',
  'Masuk…': '로그인 중…',

  // --- States / umum ---
  'Memuat…': '불러오는 중…',
  'Tidak tersedia': '정보 없음',
  'Belum pernah': '기록 없음',
  'Tidak ada data.': '데이터가 없습니다.',
  'Tidak ada hasil.': '결과가 없습니다.',
  'Gagal memuat daftar.': '목록을 불러오지 못했습니다.',
  'Belum ada data.': '데이터가 없습니다.',

  // --- Pesan "belum ada ..." yang dipakai sebagai prop <Empty text=...> ---
  'Belum ada kontak.': '연락처가 없습니다.',
  'Belum ada kualifikasi. Klik “Kualifikasi dengan AI” (butuh kunci AI di backend).':
    '아직 적격성 검사가 없습니다. “AI로 검사”를 클릭하세요 (백엔드에 AI 키 필요).',
  'Belum ada email untuk perusahaan ini.': '이 기업에 대한 이메일이 없습니다.',
  'Belum ada email. Buat draft baru di atas.': '이메일이 없습니다. 위에서 새 초안을 만드세요.',
  'Belum ada template.': '템플릿이 없습니다.',
  'Belum ada kampanye.': '캠페인이 없습니다.',
  'Email tidak ditemukan.': '이메일을 찾을 수 없습니다.',
  'Belum ada riwayat.': '기록이 없습니다.',
  'Belum ada tender yang cocok. Jalankan pencarian manual di atas.':
    '조건에 맞는 입찰이 없습니다. 위에서 수동 검색을 실행하세요.',

  // --- Tombol / dialog umum ---
  Simpan: '저장',
  Batal: '취소',
  Tutup: '닫기',
  Hapus: '삭제',
  'Ya, lanjutkan': '예, 계속',
  'Memproses…': '처리 중…',
  'Cari…': '검색…',
  'Hapus pilihan': '선택 해제',

  // --- Pagination ---
  'Menampilkan {from}–{to} dari {total}': '전체 {total}개 중 {from}–{to}',
  Sebelumnya: '이전',
  Berikutnya: '다음',
  'Halaman {page} / {pages}': '페이지 {page} / {pages}',

  // --- Notifikasi (komponen lonceng) ---
  Notifikasi: '알림',
  'Daftar notifikasi': '알림 목록',
  'Tandai semua dibaca': '모두 읽음으로 표시',
  'Belum ada notifikasi.': '알림이 없습니다.',
  'Buka Automation': '자동화 열기',

  // --- Prioritas (format.js) ---
  High: '높음',
  Medium: '보통',
  Low: '낮음',
  'Belum dianalisis': '미분석',

  // --- Status lead (format.js) ---
  New: '신규',
  Qualified: '적격',
  Contacted: '연락함',
  Responded: '응답함',
  Interested: '관심 있음',
  Converted: '전환됨',
  'Not Interested': '관심 없음',
  'Do Not Contact': '연락 금지',

  // --- Tipe email (format.js) ---
  'Perkenalan perusahaan': '회사 소개',
  'Perkenalan produk': '제품 소개',
  'Proposal kerja sama': '협업 제안',
  'Penawaran layanan': '서비스 제안',
  'Tindak lanjut': '후속 조치',

  // --- Bahasa email (format.js) ---
  'Bahasa Indonesia': '인도네시아어',
  English: '영어',
  한국어: '한국어',

  // --- Status pesan outreach (format.js) ---
  Draft: '초안',
  Disimpan: '저장됨',
  Disetujui: '승인됨',
  Terkirim: '발송됨',
  'Gagal kirim': '발송 실패',

  // --- Status job automation (format.js) ---
  Menunggu: '대기 중',
  'Dalam antrean': '대기열',
  Berjalan: '실행 중',
  Selesai: '완료',
  'Selesai sebagian': '부분 완료',
  Gagal: '실패',
  Dibatalkan: '취소됨',

  // --- Pemicu job (format.js) ---
  Terjadwal: '예약됨',
  Manual: '수동',
  'Percobaan ulang': '재시도',

  // --- Tipe automation (format.js) ---
  'Pemantauan Tender': '입찰 모니터링',
  'Penemuan Perusahaan': '기업 탐색',
  'Kualifikasi Lead': '리드 적격성 검사',
  'Pembuatan Draft Outreach': '아웃리치 초안 생성',

  // --- Hari (format.js) ---
  Senin: '월',
  Selasa: '화',
  Rabu: '수',
  Kamis: '목',
  Jumat: '금',
  Sabtu: '토',
  Minggu: '일',

  // --- Tipe jadwal (format.js) ---
  'Setiap hari': '매일',
  Mingguan: '매주',
  Bulanan: '매월',
  'Kustom (cron)': '사용자 지정 (cron)',

  // --- Kategori pengadaan (format.js CATEGORIES) ---
  'Waste Management': '폐기물 관리',
  'Recycling Equipment': '재활용 장비',
  'Industrial Machinery': '산업 기계',
  'Environmental Facilities': '환경 시설',
  'Water Treatment': '수처리',
  Other: '기타',

  // --- Label tipe notifikasi (format.js) ---
  'Automation selesai': '자동화 완료',
  'Automation selesai sebagian': '자동화 부분 완료',
  'Automation gagal': '자동화 실패',
  'Job gagal (final)': '작업 실패(최종)',
  'Tender baru': '새 입찰',
  'Deadline tender': '입찰 마감',
  'Lead baru': '새 리드',
  'Lead prioritas tinggi': '우선순위 높은 리드',
  'Draft outreach siap': '아웃리치 초안 준비됨',
}
