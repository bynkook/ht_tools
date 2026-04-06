"""
KOSIS API 데이터 수집 및 DB 캐싱 서비스.
fetch_kosis_data.py 로직을 Django 서비스 클래스로 이식.
"""
import requests

from ..models import KosisCache


KOSIS_URL = "https://kosis.kr/openapi/Param/statisticsParameterData.do"


def month_to_half(yyyymm: str) -> str:
    """YYYYMM -> YYYYHH (표준 반기: 1~6월=01, 7~12월=02)."""
    month = int(yyyymm[4:6])
    return f"{yyyymm[:4]}{'01' if month <= 6 else '02'}"


def iter_months(start: str, end: str) -> list[str]:
    """YYYYMM 범위의 모든 월 반환."""
    result = []
    year = int(start[:4])
    month = int(start[4:6])
    end_year = int(end[:4])
    end_month = int(end[4:6])

    while year < end_year or (year == end_year and month <= end_month):
        result.append(f"{year}{month:02d}")
        month += 1
        if month > 12:
            year += 1
            month = 1
    return result


def iter_half_periods(start_half: str, end_half: str) -> list[str]:
    """YYYYHH 범위의 모든 반기 반환."""
    result = []
    year = int(start_half[:4])
    half = int(start_half[4:6])
    end_year = int(end_half[:4])
    end_half_num = int(end_half[4:6])

    while year < end_year or (year == end_year and half <= end_half_num):
        result.append(f"{year}{half:02d}")
        if half == 1:
            half = 2
        else:
            year += 1
            half = 1
    return result


def half_to_month_start(half_key: str) -> str:
    return f"{half_key[:4]}{'01' if half_key[4:6] == '01' else '07'}"


def half_to_month_end(half_key: str) -> str:
    return f"{half_key[:4]}{'06' if half_key[4:6] == '01' else '12'}"


def find_missing_segments(requested_periods: list[str], cached_by_period: dict) -> list[tuple[str, str]]:
    """요청 순서를 기준으로 누락 구간을 연속 세그먼트로 묶는다."""
    segments = []
    segment_start = None

    for period in requested_periods:
        if period not in cached_by_period:
            if segment_start is None:
                segment_start = period
        elif segment_start is not None:
            segments.append((segment_start, prev_period))
            segment_start = None
        prev_period = period

    if segment_start is not None:
        segments.append((segment_start, requested_periods[-1]))
    return segments


class KosisService:
    def __init__(self, api_key: str):
        self.api_key = api_key

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def get_ppi(self, start: str, end: str) -> list[dict]:
        """
        생산자물가지수(공산품) 월별 데이터 반환.
        DB 영구 캐시를 우선 사용하고, 누락 월만 추가 호출하여 병합 반환한다.
        Returns: [{'시점': 'YYYYMM', '공산품': float}, ...]
        """
        requested_periods = iter_months(start, end)
        cached_by_period = self._collect_cached_points(KosisCache.DATA_TYPE_PPI, requested_periods)

        for missing_start, missing_end in find_missing_segments(requested_periods, cached_by_period):
            raw = self._fetch_ppi(missing_start, missing_end)
            normalized = self._normalize_ppi(raw)
            self._save_cache(KosisCache.DATA_TYPE_PPI, missing_start, missing_end, normalized)
            for item in normalized:
                period = item.get('시점')
                if period in requested_periods:
                    cached_by_period[period] = item

        return [cached_by_period[period] for period in requested_periods if period in cached_by_period]

    def get_wage(self, start: str, end: str) -> list[dict]:
        """
        시중노임단가(일반공사직종) 반기 데이터 반환.
        DB 영구 캐시를 우선 사용하고, 누락 반기만 추가 호출하여 병합 반환한다.
        Returns: [{'시점': 'YYYYHH'(예: '202101'), '값': int}, ...]
        시점은 반기 단위: 202101=2021년 상반기, 202102=2021년 하반기
        """
        start_half = month_to_half(start)
        end_half = month_to_half(end)
        requested_periods = iter_half_periods(start_half, end_half)
        cached_by_period = self._collect_cached_points(KosisCache.DATA_TYPE_WAGE, requested_periods)

        for missing_start, missing_end in find_missing_segments(requested_periods, cached_by_period):
            raw = self._fetch_wage_halves(missing_start, missing_end)
            normalized = self._normalize_wage(raw)
            self._save_cache(
                KosisCache.DATA_TYPE_WAGE,
                half_to_month_start(missing_start),
                half_to_month_end(missing_end),
                normalized,
            )
            for item in normalized:
                period = item.get('시점')
                if period in requested_periods:
                    cached_by_period[period] = item

        return [cached_by_period[period] for period in requested_periods if period in cached_by_period]

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    def _collect_cached_points(self, data_type: str, requested_periods: list[str]) -> dict[str, dict]:
        requested_set = set(requested_periods)
        merged: dict[str, dict] = {}
        caches = KosisCache.objects.filter(data_type=data_type).order_by('fetched_at', 'id')

        for cache in caches:
            for item in cache.payload or []:
                period = item.get('시점')
                if period in requested_set:
                    merged[period] = item
        return merged

    def _save_cache(self, data_type: str, start: str, end: str, payload: list):
        KosisCache.objects.update_or_create(
            data_type=data_type,
            period_start=start,
            period_end=end,
            defaults={'payload': payload},
        )

    # ------------------------------------------------------------------
    # KOSIS API calls
    # ------------------------------------------------------------------

    def _fetch_raw(self, params: dict, label: str) -> list:
        params['apiKey'] = self.api_key
        try:
            response = requests.get(KOSIS_URL, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            if not data or not isinstance(data, list):
                raise ValueError(f"{label}: KOSIS API가 빈 응답을 반환했습니다.")
            return data
        except requests.RequestException as e:
            raise ConnectionError(f"{label}: KOSIS API 호출 실패 - {e}") from e

    def _fetch_ppi(self, start: str, end: str) -> list:
        params = {
            "method": "getList",
            "itmId": "13103134604999 ",
            "objL1": "13102134604ACC_CD.*AA 13102134604ACC_CD.3AA ",
            "objL2": "", "objL3": "", "objL4": "", "objL5": "",
            "objL6": "", "objL7": "", "objL8": "",
            "format": "json",
            "jsonVD": "Y",
            "prdSe": "M",
            "startPrdDe": start,
            "endPrdDe": end,
            "outputFields": "TBL_ID TBL_NM OBJ_ID OBJ_NM NM ITM_ID ITM_NM UNIT_NM PRD_SE PRD_DE LST_CHN_DE ",
            "orgId": "301",
            "tblId": "DT_404Y014",
        }
        return self._fetch_raw(params, f"PPI {start}~{end}")

    def _fetch_wage(self, start: str, end: str) -> list:
        start_half = month_to_half(start)
        end_half = month_to_half(end)
        return self._fetch_wage_halves(start_half, end_half)

    def _fetch_wage_halves(self, start_half: str, end_half: str) -> list:
        params = {
            "method": "getList",
            "itmId": "16365AAC8 ",
            "objL1": "15365AG5AB ",
            "objL2": "", "objL3": "", "objL4": "", "objL5": "",
            "objL6": "", "objL7": "", "objL8": "",
            "format": "json",
            "jsonVD": "Y",
            "prdSe": "S",
            "startPrdDe": start_half,
            "endPrdDe": end_half,
            "outputFields": "TBL_ID TBL_NM OBJ_ID OBJ_NM NM ITM_ID ITM_NM UNIT_NM PRD_SE PRD_DE LST_CHN_DE ",
            "orgId": "365",
            "tblId": "TX_36504_A000",
        }
        return self._fetch_raw(params, f"Wage {start_half}~{end_half}")

    # ------------------------------------------------------------------
    # Normalization
    # ------------------------------------------------------------------

    def _normalize_ppi(self, raw: list) -> list[dict]:
        """
        KOSIS 응답에서 공산품(C1_NM) 기준 월별 PPI 추출.
        Returns: [{'시점': 'YYYYMM', '공산품': float}, ...]
        """
        result = {}
        for item in raw:
            period = item.get('PRD_DE', '')
            name = item.get('C1_NM', '')
            value = item.get('DT', '')
            if '공산품' in name:
                try:
                    result[period] = {'시점': period, '공산품': float(value)}
                except (ValueError, TypeError):
                    pass
        return sorted(result.values(), key=lambda x: x['시점'])

    def _normalize_wage(self, raw: list) -> list[dict]:
        """
        KOSIS 응답에서 일반공사직종 평균임금 반기 데이터 추출.
        Returns: [{'시점': 'YYYYHH', '값': int}, ...]
        시점 예시: '202101' = 2021년 1반기(상반기), '202102' = 2021년 2반기(하반기)
        """
        result = {}
        for item in raw:
            period = item.get('PRD_DE', '')
            구분 = item.get('C1_NM', '')
            value = item.get('DT', '')
            if '일반공사' in 구분 or not 구분:
                try:
                    result[period] = {'시점': period, '값': int(float(value))}
                except (ValueError, TypeError):
                    pass
        return sorted(result.values(), key=lambda x: x['시점'])
