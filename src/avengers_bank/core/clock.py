from datetime import date, datetime, timedelta, timezone

# 한국은 서머타임이 없어서 고정 +9시간. zoneinfo는 Windows에서 tzdata 패키지가 따로 필요해서 쓰지 않는다
KST = timezone(timedelta(hours=9), "KST")


def today_kst() -> date:
    """판매 기간·만기 같은 '날짜' 판단은 서버 시간대(컨테이너는 UTC)가 아니라 한국 날짜로 한다."""
    return datetime.now(KST).date()
