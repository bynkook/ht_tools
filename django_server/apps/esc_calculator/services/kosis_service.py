"""
KOSIS API 데이터 수집 및 DB 캐싱 서비스.
fetch_kosis_data.py 로직을 Django 서비스 클래스로 이식.
"""
import requests
from datetime import datetime

from ..models import KosisCache


KOSIS_URL = "https://kosis.kr/openapi/Param/statisticsParameterData.do"


class KosisService:
    def __init__(self, api_key: str):
        self.api_key = api_key

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def get_ppi(self, start: str, end: str) -> list[dict]:
        """
        생산자물가지수(공산품) 월별 데이터 반환.
        캐시 hit: DB 반환, miss: KOSIS API 호출 후 DB 저장.
        Returns: [{'시점': 'YYYYMM', '공산품': float}, ...]
        """
        cached = self._get_cache(KosisCache.DATA_TYPE_PPI, start, end)
        if cached is not None:
            return cached

        raw = self._fetch_ppi(start, end)
        normalized = self._normalize_ppi(raw)
        self._save_cache(KosisCache.DATA_TYPE_PPI, start, end, normalized)
        return normalized

    def get_wage(self, start: str, end: str) -> list[dict]:
        """
        시중노임단가(일반공사직종) 반기 데이터 반환.
        Returns: [{'시점': 'YYYYHH'(예: '202101'), '값': int}, ...]
        시점은 반기 단위: 202101=2021년 상반기, 202102=2021년 하반기
        """
        cached = self._get_cache(KosisCache.DATA_TYPE_WAGE, start, end)
        if cached is not None:
            return cached

        raw = self._fetch_wage(start, end)
        normalized = self._normalize_wage(raw)
        self._save_cache(KosisCache.DATA_TYPE_WAGE, start, end, normalized)
        return normalized

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    def _get_cache(self, data_type: str, start: str, end: str):
        try:
            cache = KosisCache.objects.get(
                data_type=data_type,
                period_start=start,
                period_end=end,
            )
            return cache.payload
        except KosisCache.DoesNotExist:
            return None

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
        # YYYYMM → YYYYHH 변환 (시중노임단가 공시 기준):
        #   1~8월  → YYYY01 (상반기 공시 적용)
        #   9~12월 → YYYY02 (하반기 공시 적용)
        # 검증: 202107(7월) → 202101, 202109(9월) → 202102, 202201(1월) → 202201
        def to_half(yyyymm: str) -> str:
            return f"{yyyymm[:4]}{'02' if int(yyyymm[4:6]) >= 9 else '01'}"

        start_half = to_half(start)   # e.g. 202107 → 202102
        end_half   = to_half(end)     # e.g. 202204 → 202201
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
