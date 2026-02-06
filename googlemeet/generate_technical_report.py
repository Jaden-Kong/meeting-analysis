#!/usr/bin/env python3
"""
데일리 미팅 리포트 생성기
Usage: python generate_daily_report.py --date 2026-02-03
"""

import csv
import sys
import re
import argparse
from collections import defaultdict
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


def replace_names_in_text(text: str) -> str:
    """텍스트 내 풀네임을 짧은 이름으로 변환"""
    for full, short in NAME_MAP.items():
        text = text.replace(full, short)
    return text


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


def truncate_to_sentence(text: str, max_len: int = 250) -> str:
    """
    텍스트를 문장 단위로 자르기
    - 문장 종결 패턴을 찾아 자연스럽게 끊음
    - 소수점(0.01 등)에서 끊기지 않도록 처리
    - 적절한 문장 종결이 없으면 단어 경계에서 ...으로 마무리
    """
    if len(text) <= max_len:
        return text

    truncated = text[:max_len]

    # 문장 종결 패턴 (숫자 뒤의 점 제외)
    sentence_end_patterns = [
        r'다\.\s', r'요\.\s', r'음\.\s', r'임\.\s',  # 한국어 + 공백
        r'다\.$', r'요\.$', r'음\.$', r'임\.$',  # 한국어 문장 끝
        r'\)\.\s', r'\)\.$',  # 괄호 뒤 마침표
        r'[a-zA-Z]\.\s', r'[a-zA-Z]\.$',  # 영어 + 마침표
        r'\?\s', r'\?$', r'!\s', r'!$',  # 물음표/느낌표
    ]

    last_end = -1
    for pattern in sentence_end_patterns:
        matches = list(re.finditer(pattern, truncated))
        if matches:
            pos = matches[-1].end()
            if pos > last_end:
                last_end = pos

    # 문장 종결 위치가 충분히 뒤에 있으면 거기서 자르기
    if last_end > 80:
        return text[:last_end].strip()

    # 폴백: 숫자 앞이 아닌 마지막 마침표 찾기
    for i in range(len(truncated) - 1, 50, -1):
        if truncated[i] == '.':
            if i > 0 and not truncated[i-1].isdigit():
                return text[:i + 1].strip()

    # 최종 폴백: 단어 경계에서 ...으로 마무리
    last_space = truncated.rfind(' ')
    if last_space > 100:
        return text[:last_space].strip() + "..."

    return truncated.strip() + "..."


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


def extract_content_sections(content: str) -> dict:
    """회의록에서 요약, 결정사항, 진전사항, 이슈, 액션아이템 추출"""
    content = content.replace('\\r\\n', '\n').replace('\r\n', '\n')

    result = {
        'summary': '',
        'decisions': [],
        'progress': [],
        'issues': [],
        'actions': []
    }

    # 요약 추출
    summary_patterns = [
        r'요약\s*\n(.+?)(?=\n\n세부정보|\n\nDetails|\n\n\n)',
        r'Summary\s*\n(.+?)(?=\n\nDetails|\n\n\n)',
    ]

    for pattern in summary_patterns:
        match = re.search(pattern, content, re.DOTALL)
        if match:
            result['summary'] = replace_names_in_text(match.group(1).strip())
            break

    # 세부정보 추출
    details_patterns = [
        r'세부정보\s*\n(.+?)(?=\n추천하는 다음 단계|\n\n\n|$)',
        r'Details\s*\n(.+?)(?=\nSuggested next steps|\n\n\n|$)',
    ]

    details_text = ''
    for pattern in details_patterns:
        match = re.search(pattern, content, re.DOTALL)
        if match:
            details_text = match.group(1).strip()
            break

    if details_text:
        bullets = re.findall(r'\* ([^\n]+(?:\n(?!\*)[^\n]+)*)', details_text)

        for bullet in bullets:
            bullet_lower = bullet.lower()
            bullet_clean = replace_names_in_text(bullet)
            # 첫 줄 또는 전체 불릿 내용을 문장 단위로 자르기
            first_line = bullet_clean.split('\n')[0]

            # 결정사항
            if any(kw in bullet_lower for kw in ['결정', 'decided', 'agreed', 'confirmed', 'approved', 'will be', '하기로']):
                result['decisions'].append(first_line)
            # 진전사항
            elif any(kw in bullet_lower for kw in ['완료', 'completed', 'finished', 'done', '80%', '90%', 'progress', 'implemented', '진행']):
                result['progress'].append(first_line)
            # 이슈
            elif any(kw in bullet_lower for kw in ['이슈', 'issue', 'problem', 'blocker', 'fail', '문제', 'concern', 'risk', 'missing', '우려', 'challenge']):
                result['issues'].append(first_line)

    # 액션아이템 추출
    action_patterns = [
        r'추천하는 다음 단계\s*\n(.+?)(?=\n\n|$)',
        r'Suggested next steps\s*\n(.+?)(?=\n\n|$)',
    ]

    for pattern in action_patterns:
        match = re.search(pattern, content, re.DOTALL)
        if match:
            steps = match.group(1).strip()
            items = re.findall(r'\* (.+)', steps)
            for item in items:
                result['actions'].append(replace_names_in_text(item))

    return result


# ============================================================================
# 리포트 생성
# ============================================================================

def load_meetings(csv_files: list, target_date: str) -> list:
    """CSV 파일들에서 특정 날짜의 회의 데이터 로드"""
    meetings = []

    # 날짜 패턴 (2026/02/03 또는 2026년 2월 3일)
    date_patterns = [
        target_date.replace('-', '/'),  # 2026/02/03
        f"{target_date[:4]}년 {int(target_date[5:7])}월 {int(target_date[8:10])}일"  # 2026년 2월 3일
    ]

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
                    if not any(dp in name for dp in date_patterns):
                        continue

                    # 빈 회의 건너뛰기
                    if "summary wasn't produced" in content.lower():
                        continue

                    # 언어 감지
                    is_korean = '스크립트' in content or '회의록' in content
                    lang = 'ko' if is_korean else 'en'

                    # 파싱
                    speakers = parse_transcript_speakers(content)
                    sections = extract_content_sections(content)

                    if not speakers and not sections['summary']:
                        continue

                    # 화자 정보 정리
                    speaker_list = []
                    for sp, char_count in speakers.items():
                        est_seconds = estimate_talk_time_seconds(char_count, lang)
                        short_name = get_short_name(sp)
                        speaker_list.append({'name': short_name, 'seconds': est_seconds})
                    speaker_list.sort(key=lambda x: x['seconds'], reverse=True)

                    # 회의명 정리
                    short_name = name
                    if ' – ' in short_name:
                        short_name = short_name.split(' – ')[0]
                    if ' - Gemini' in short_name:
                        short_name = short_name.split(' - Gemini')[0]
                    if 'KST에 시작한 회의' in short_name:
                        short_name = short_name.replace('에 시작한 회의', '')

                    meetings.append({
                        'name': short_name.strip(),
                        'lang': lang,
                        'speakers': speaker_list,
                        'summary': sections['summary'],
                        'decisions': sections['decisions'],
                        'progress': sections['progress'],
                        'issues': sections['issues'],
                        'actions': sections['actions']
                    })
        except FileNotFoundError:
            print(f"⚠️  파일 없음: {csv_file}")
            continue

    return meetings


def generate_report(meetings: list, target_date: str) -> str:
    """노션용 마크다운 리포트 생성"""

    # 날짜 포맷
    year, month, day = target_date.split('-')
    weekdays = ['월', '화', '수', '목', '금', '토', '일']
    from datetime import date
    weekday = weekdays[date(int(year), int(month), int(day)).weekday()]
    date_str = f"{year}년 {int(month)}월 {int(day)}일 ({weekday})"

    output = []
    output.append("# 📰 데일리 미팅 리포트")
    output.append("")
    output.append(f"## 📅 {date_str}")
    output.append("")
    output.append(f"> 총 **{len(meetings)}개** 회의 분석 | 자동 생성 리포트")
    output.append("")
    output.append("---")
    output.append("")

    # 요약 테이블
    output.append("## 📊 오늘의 미팅 요약")
    output.append("")
    output.append("| 회의 | 주요 참여자 | 총 발화시간 |")
    output.append("|------|-------------|-------------|")

    for m in meetings:
        top_speakers = ', '.join([s['name'] for s in m['speakers'][:3]])
        total_secs = sum(s['seconds'] for s in m['speakers'])
        time_str = format_time(total_secs)
        meeting_short = m['name'][:35] + '...' if len(m['name']) > 35 else m['name']
        output.append(f"| {meeting_short} | {top_speakers} | {time_str} |")

    output.append("")
    output.append("---")
    output.append("")

    # 개별 회의 리포트
    for i, m in enumerate(meetings, 1):
        output.append(f"## 📋 {i}. {m['name']}")
        output.append("")

        # 참여자 및 발화시간
        if m['speakers']:
            output.append("### 👥 참여자 및 발화시간")
            output.append("")
            max_time = m['speakers'][0]['seconds'] if m['speakers'] else 1

            for sp in m['speakers']:
                if sp['seconds'] < 5:
                    continue
                bar_len = int((sp['seconds'] / max_time) * 15)
                bar = '█' * bar_len if bar_len > 0 else '▏'
                time_str = format_time(sp['seconds'])
                output.append(f"- **{sp['name']}**: {time_str} {bar}")

            output.append("")

        # 요약
        if m['summary']:
            output.append("### 📌 요약")
            output.append("")
            summary = truncate_to_sentence(m['summary'], 500)
            output.append(f"> {summary}")
            output.append("")

        # 결정사항
        if m['decisions']:
            output.append("### ✅ 결정 사항")
            output.append("")
            for item in m['decisions'][:3]:
                output.append(f"- {truncate_to_sentence(item, 200)}")
            output.append("")

        # 진전사항
        if m['progress']:
            output.append("### 📈 진전 사항")
            output.append("")
            for item in m['progress'][:3]:
                output.append(f"- {truncate_to_sentence(item, 200)}")
            output.append("")

        # 이슈
        if m['issues']:
            output.append("### ⚠️ 이슈 및 블로커")
            output.append("")
            for item in m['issues'][:3]:
                output.append(f"- {truncate_to_sentence(item, 200)}")
            output.append("")

        # 액션아이템
        if m['actions']:
            output.append("### 📋 액션 아이템")
            output.append("")
            for action in m['actions'][:5]:
                output.append(f"- [ ] {truncate_to_sentence(action, 200)}")
            output.append("")

        output.append("---")
        output.append("")

    output.append("")
    output.append("*📝 본 리포트는 자동 생성되었습니다.*")

    return '\n'.join(output)


# ============================================================================
# 메인
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description='데일리 미팅 리포트 생성기')
    parser.add_argument('--date', '-d', required=True, help='분석할 날짜 (YYYY-MM-DD)')
    parser.add_argument('--output', '-o', help='출력 파일 경로 (기본: daily_report_YYYYMMDD_notion.md)')
    parser.add_argument('--csv', '-c', nargs='+', default=DEFAULT_CSV_FILES, help='입력 CSV 파일들')

    args = parser.parse_args()

    # 날짜 검증
    try:
        from datetime import datetime
        datetime.strptime(args.date, '%Y-%m-%d')
    except ValueError:
        print(f"❌ 잘못된 날짜 형식: {args.date} (YYYY-MM-DD 형식 필요)")
        sys.exit(1)

    print(f"📅 {args.date} 회의록 분석 중...")

    # 회의 데이터 로드
    meetings = load_meetings(args.csv, args.date)

    if not meetings:
        print(f"⚠️  {args.date}에 해당하는 회의를 찾을 수 없습니다.")
        sys.exit(0)

    print(f"✅ {len(meetings)}건의 회의 발견")

    # 리포트 생성
    report = generate_report(meetings, args.date)

    # 출력 파일 결정
    if args.output:
        output_path = args.output
    else:
        date_compact = args.date.replace('-', '')
        output_path = f"daily_report_{date_compact}_notion.md"

    # 저장
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(report)

    print(f"✅ 리포트 저장 완료: {output_path}")
    print()
    print("=" * 60)
    print(report[:2000])
    if len(report) > 2000:
        print("...")
        print(f"(총 {len(report)} 문자)")


if __name__ == '__main__':
    main()
