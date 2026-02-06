#!/usr/bin/env python3
"""
발화시간 분석기
Usage:
  python generate_talk_time.py --date 2026-02-03
  python generate_talk_time.py --start 2026-02-01 --end 2026-02-03
"""

import csv
import sys
import re
import argparse
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

csv.field_size_limit(sys.maxsize)

# ============================================================================
# 설정
# ============================================================================

# 이름 매핑 (풀네임 -> 짧은 이름)
NAME_MAP = {
    'YEONGJU BAK': 'Zena',
    'Jason Hwang': 'Jason',
    'Harvey Jo': 'Harvey',
    'Aryan Soni': 'Aryan',
    'Suhyeon Lee': 'Suhyeon',
    'Sahil Wasnik': 'Sahil',
    'Singh Shailendra': 'Singh',
    'Praveen Surendran': 'Praveen',
    'Manish Kumar': 'Manish',
    'Mehdi Beriane': 'Mehdi',
    'Nam Tiến': 'Nam',
    'Bernard Lee': 'Bernard',
    'Jaden Lee': 'Jaden',
    'Jaden Kong': 'Jaden',
    'Irene Kim': 'Irene',
    'Irene Bae': 'Irene',
    'Kevin Lee': 'Kevin',
    'Kevin Kim': 'Kevin',
    'Theo Lee': 'Theo',
    'Monica Kim': 'Monica',
    'Eugenie Nguyen': 'Eugenie',
    'Eugenie Park': 'Eugenie',
    'George Negru': 'George',
}

# 제외할 패턴 (회의명, 메타데이터 등)
EXCLUDED_PATTERNS = [
    r'^Project\s', r'^DRB\s', r'^TRH\s', r'^Upgrade\s', r'^Meeting\s',
    r'^Notes\s', r'^Attachments', r'^Invited', r'^Summary', r'^Details',
    r'^Recording', r'^Transcript', r'^Gemini', r'Seminar'
]

# 기본 CSV 파일 목록
DEFAULT_CSV_FILES = [
    'irene.recordings.csv',
    'jaden.recordings.csv',
    'shared.recordings.csv'
]

# ============================================================================
# 유틸리티 함수
# ============================================================================

def get_short_name(full_name: str) -> str:
    """풀네임을 짧은 이름으로 변환"""
    if full_name in NAME_MAP:
        return NAME_MAP[full_name]
    if ' ' in full_name:
        return full_name.split()[0]
    return full_name


def is_valid_speaker(name: str) -> bool:
    """유효한 화자인지 확인"""
    for pattern in EXCLUDED_PATTERNS:
        if re.match(pattern, name, re.IGNORECASE):
            return False
    if name in NAME_MAP:
        return True
    words = name.split()
    if len(words) != 2:
        return False
    for w in words:
        if len(w) < 2 or len(w) > 15:
            return False
        if not w[0].isupper():
            return False
        if not re.match(r'^[A-Za-zÀ-ỹ]+$', w):
            return False
    return True


def format_time(seconds: float) -> str:
    """초를 'M분 S초' 형식으로 변환"""
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}분 {secs}초"


def estimate_talk_time_seconds(char_count: int, lang: str = 'en') -> float:
    """글자 수로 발화시간 추정"""
    if lang == 'ko':
        return char_count / 5  # 한국어: 초당 약 5자
    else:
        return char_count / 15  # 영어: 초당 약 15자


def get_date_range(start_date: str, end_date: str) -> list:
    """날짜 범위 생성"""
    start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d')
    dates = []
    current = start
    while current <= end:
        dates.append(current.strftime('%Y-%m-%d'))
        current += timedelta(days=1)
    return dates


# ============================================================================
# 파싱 함수
# ============================================================================

def parse_transcript_speakers(content: str) -> dict:
    """트랜스크립트에서 화자별 글자 수 추출"""
    speakers = defaultdict(int)
    content = content.replace('\\r\\n', '\n').replace('\r\n', '\n').replace('\r', '\n')

    transcript_markers = ['📖 Transcript', '📖 스크립트']
    transcript_start = -1
    for marker in transcript_markers:
        pos = content.find(marker)
        if pos != -1:
            transcript_start = pos
            break

    if transcript_start == -1:
        return {}

    transcript_text = content[transcript_start:]
    speaker_pattern = r'^([A-Za-zÀ-ỹ][A-Za-zÀ-ỹ\s]{1,28}):\s*(.+)$'

    for line in transcript_text.split('\n'):
        line = line.strip()
        if not line:
            continue
        sp_match = re.match(speaker_pattern, line)
        if sp_match:
            speaker_name = sp_match.group(1).strip()
            dialogue = sp_match.group(2).strip()
            if not is_valid_speaker(speaker_name):
                continue
            if len(dialogue) < 2:
                continue
            speakers[speaker_name] += len(dialogue)

    return dict(speakers)


def check_date_match(name: str, target_dates: list) -> bool:
    """회의명에서 날짜가 타겟 날짜 범위에 포함되는지 확인"""
    for target_date in target_dates:
        date_patterns = [
            target_date.replace('-', '/'),  # 2026/02/03
            f"{target_date[:4]}년 {int(target_date[5:7])}월 {int(target_date[8:10])}일"  # 2026년 2월 3일
        ]
        for dp in date_patterns:
            if dp in name:
                return True
    return False


# ============================================================================
# 메인 분석 함수
# ============================================================================

def analyze_talk_time(csv_files: list, target_dates: list) -> dict:
    """CSV 파일들에서 발화시간 분석"""
    all_speakers = defaultdict(float)
    meeting_count = 0

    for csv_file in csv_files:
        try:
            with open(csv_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)

                for row in reader:
                    name = row.get('name', '')
                    content = row.get('content', '')

                    if not content:
                        continue

                    # 날짜 확인
                    if not check_date_match(name, target_dates):
                        continue

                    # 빈 회의 건너뛰기
                    if "summary wasn't produced" in content.lower():
                        continue

                    # 언어 감지
                    is_korean = '스크립트' in content or '회의록' in content
                    lang = 'ko' if is_korean else 'en'

                    # 화자별 글자 수 추출
                    speakers = parse_transcript_speakers(content)
                    if not speakers:
                        continue

                    meeting_count += 1

                    # 발화시간 추정
                    for sp, char_count in speakers.items():
                        est_seconds = estimate_talk_time_seconds(char_count, lang)
                        short_name = get_short_name(sp)
                        all_speakers[short_name] += est_seconds

        except FileNotFoundError:
            print(f"⚠️  파일 없음: {csv_file}")
            continue

    return dict(all_speakers), meeting_count


def generate_csv_output(speaker_list: list, output_path: str, format_type: str = 'formatted'):
    """CSV 파일 생성 (speaker_list: [{'name': str, 'seconds': float}, ...])"""
    with open(output_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)

        if format_type == 'seconds':
            writer.writerow(['이름', '발화시간(초)'])
            for sp in speaker_list:
                writer.writerow([sp['name'], round(sp['seconds'], 1)])
        else:
            writer.writerow(['이름', '발화시간'])
            for sp in speaker_list:
                writer.writerow([sp['name'], format_time(sp['seconds'])])


def print_results(speakers: dict, target_dates: list, meeting_count: int):
    """결과 출력"""
    if len(target_dates) == 1:
        date_str = target_dates[0]
    else:
        date_str = f"{target_dates[0]} ~ {target_dates[-1]}"

    print()
    print("=" * 60)
    print(f"📊 발화시간 분석 결과: {date_str}")
    print(f"📅 분석 대상 회의: {meeting_count}건")
    print("=" * 60)
    print()

    sorted_speakers = sorted(speakers.items(), key=lambda x: x[1], reverse=True)
    max_time = sorted_speakers[0][1] if sorted_speakers else 1

    total_seconds = sum(s[1] for s in sorted_speakers)

    print(f"{'이름':<15} {'발화시간':<12} {'비율':<8} 그래프")
    print("-" * 60)

    for name, seconds in sorted_speakers:
        if seconds < 5:
            continue
        time_str = format_time(seconds)
        ratio = (seconds / total_seconds * 100) if total_seconds > 0 else 0
        bar_len = int((seconds / max_time) * 20)
        bar = '█' * bar_len if bar_len > 0 else '▏'
        print(f"{name:<15} {time_str:<12} {ratio:>5.1f}%  {bar}")

    print("-" * 60)
    print(f"{'합계':<15} {format_time(total_seconds):<12} 100.0%")
    print()


# ============================================================================
# 메인
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description='발화시간 분석기')
    parser.add_argument('--date', '-d', help='분석할 날짜 (YYYY-MM-DD)')
    parser.add_argument('--start', '-s', help='시작 날짜 (YYYY-MM-DD)')
    parser.add_argument('--end', '-e', help='종료 날짜 (YYYY-MM-DD)')
    parser.add_argument('--output', '-o', help='출력 파일 경로 (기본: talk_time_YYYYMMDD.csv)')
    parser.add_argument('--seconds', action='store_true', help='초 단위로 출력')
    parser.add_argument('--csv', '-c', nargs='+', default=DEFAULT_CSV_FILES, help='입력 CSV 파일들')
    parser.add_argument('--no-csv', action='store_true', help='CSV 파일 생성 안함')

    args = parser.parse_args()

    # 날짜 범위 결정
    if args.date:
        target_dates = [args.date]
    elif args.start and args.end:
        target_dates = get_date_range(args.start, args.end)
    else:
        print("❌ 날짜를 지정해주세요. --date 또는 --start/--end 사용")
        print("   예: python generate_talk_time.py --date 2026-02-03")
        print("   예: python generate_talk_time.py --start 2026-02-01 --end 2026-02-03")
        sys.exit(1)

    # 날짜 검증
    for d in target_dates:
        try:
            datetime.strptime(d, '%Y-%m-%d')
        except ValueError:
            print(f"❌ 잘못된 날짜 형식: {d} (YYYY-MM-DD 형식 필요)")
            sys.exit(1)

    print(f"📅 {target_dates[0]} ~ {target_dates[-1]} 회의록 분석 중..." if len(target_dates) > 1 else f"📅 {target_dates[0]} 회의록 분석 중...")

    # 발화시간 분석
    speakers, meeting_count = analyze_talk_time(args.csv, target_dates)

    if not speakers:
        print(f"⚠️  해당 기간에 회의를 찾을 수 없습니다.")
        sys.exit(0)

    # 결과 출력
    print_results(speakers, target_dates, meeting_count)

    # CSV 저장
    if not args.no_csv:
        # 출력 파일명 결정
        if args.output:
            output_path = args.output
        else:
            if len(target_dates) == 1:
                date_compact = target_dates[0].replace('-', '')
                output_path = f"talk_time_{date_compact}.csv"
            else:
                start_compact = target_dates[0].replace('-', '')[4:]  # MMDD
                end_compact = target_dates[-1].replace('-', '')[4:]    # MMDD
                output_path = f"talk_time_{start_compact}_{end_compact}.csv"

        # 데이터 정리
        speaker_list = [{'name': name, 'seconds': secs} for name, secs in speakers.items()]
        speaker_list.sort(key=lambda x: x['seconds'], reverse=True)

        # CSV 저장
        format_type = 'seconds' if args.seconds else 'formatted'
        generate_csv_output(speaker_list, output_path, format_type)
        print(f"✅ CSV 저장 완료: {output_path}")

        # 초 단위 CSV도 저장 (기본 형식인 경우)
        if not args.seconds:
            seconds_path = output_path.replace('.csv', '_seconds.csv')
            generate_csv_output(speaker_list, seconds_path, 'seconds')
            print(f"✅ CSV 저장 완료: {seconds_path}")


if __name__ == '__main__':
    main()
