from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status

from .models import EscProject, KosisCache
from .services.kosis_service import KosisService

User = get_user_model()


# ---------------------------------------------------------------------------
# KosisService 정규화 단위 테스트
# ---------------------------------------------------------------------------

RAW_PPI_SAMPLE = [
    {'PRD_DE': '202107', 'C1_NM': '공산품', 'DT': '111.81'},
    {'PRD_DE': '202107', 'C1_NM': '총지수', 'DT': '105.00'},   # 제외 대상
    {'PRD_DE': '202108', 'C1_NM': '공산품', 'DT': '112.50'},
    {'PRD_DE': '202109', 'C1_NM': '공산품', 'DT': ''},          # 빈값: 무시
]

RAW_WAGE_SAMPLE = [
    {'PRD_DE': '202101', 'C1_NM': '일반공사', 'DT': '178321'},
    {'PRD_DE': '202101', 'C1_NM': '전기공사', 'DT': '200000'},  # 제외 대상
    {'PRD_DE': '202102', 'C1_NM': '일반공사', 'DT': '183500'},
    {'PRD_DE': '202103', 'C1_NM': '일반공사', 'DT': ''},        # 빈값: 무시
]


class TestKosisServiceNormalize(TestCase):
    def setUp(self):
        self.svc = KosisService(api_key='test_key')

    def test_normalize_ppi_filters_to_industrial_goods(self):
        result = self.svc._normalize_ppi(RAW_PPI_SAMPLE)
        # 공산품 행만 포함 (총지수 제외), 빈값 제외
        self.assertEqual(len(result), 2)
        periods = [r['시점'] for r in result]
        self.assertIn('202107', periods)
        self.assertIn('202108', periods)
        self.assertNotIn('202109', periods)

    def test_normalize_ppi_value_type(self):
        result = self.svc._normalize_ppi(RAW_PPI_SAMPLE)
        for item in result:
            self.assertIsInstance(item['공산품'], float)

    def test_normalize_ppi_sorted_by_period(self):
        result = self.svc._normalize_ppi(RAW_PPI_SAMPLE)
        periods = [r['시점'] for r in result]
        self.assertEqual(periods, sorted(periods))

    def test_normalize_wage_filters_to_general_construction(self):
        result = self.svc._normalize_wage(RAW_WAGE_SAMPLE)
        # 일반공사 행만 포함, 빈값 제외
        self.assertEqual(len(result), 2)
        periods = [r['시점'] for r in result]
        self.assertIn('202101', periods)
        self.assertIn('202102', periods)
        self.assertNotIn('202103', periods)

    def test_normalize_wage_value_type(self):
        result = self.svc._normalize_wage(RAW_WAGE_SAMPLE)
        for item in result:
            self.assertIsInstance(item['값'], int)

    def test_normalize_wage_sorted_by_period(self):
        result = self.svc._normalize_wage(RAW_WAGE_SAMPLE)
        periods = [r['시점'] for r in result]
        self.assertEqual(periods, sorted(periods))


# ---------------------------------------------------------------------------
# KosisService DB 캐싱 테스트
# ---------------------------------------------------------------------------

class TestKosisServiceCache(TestCase):
    def setUp(self):
        self.svc = KosisService(api_key='test_key')

    def test_cache_hit_returns_without_api_call(self):
        payload = [
            {'시점': '202107', '공산품': 111.81},
            {'시점': '202108', '공산품': 112.50},
        ]
        KosisCache.objects.create(
            data_type=KosisCache.DATA_TYPE_PPI,
            period_start='202107',
            period_end='202108',
            payload=payload,
        )
        with patch.object(self.svc, '_fetch_ppi') as mock_fetch:
            result = self.svc.get_ppi('202107', '202108')
        mock_fetch.assert_not_called()
        self.assertEqual(result, payload)

    @patch('apps.esc_calculator.services.kosis_service.requests.get')
    def test_cache_miss_calls_api_and_saves(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = RAW_PPI_SAMPLE
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        self.svc.get_ppi('202107', '202108')

        mock_get.assert_called_once()
        self.assertEqual(KosisCache.objects.filter(data_type=KosisCache.DATA_TYPE_PPI).count(), 1)

    @patch('apps.esc_calculator.services.kosis_service.requests.get')
    def test_api_connection_error_raises(self, mock_get):
        import requests as req_lib
        mock_get.side_effect = req_lib.ConnectionError("timeout")
        with self.assertRaises(ConnectionError):
            self.svc.get_ppi('202107', '202108')

    @patch('apps.esc_calculator.services.kosis_service.requests.get')
    def test_wage_fetch_uses_semiannual_period_codes(self, mock_get):
        """YYYYMM → YYYYHH 변환: 1~6월=상반기(01), 7~12월=하반기(02)"""
        mock_response = MagicMock()
        mock_response.json.return_value = RAW_WAGE_SAMPLE
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        # start=202106(6월 → 202101), end=202107(7월 → 202102)
        self.svc.get_wage('202106', '202107')

        call_params = mock_get.call_args[1]['params']
        self.assertEqual(call_params['startPrdDe'], '202101')   # 상반기 2021
        self.assertEqual(call_params['endPrdDe'],   '202102')   # 하반기 2021

    @patch('apps.esc_calculator.services.kosis_service.requests.get')
    def test_wage_fetch_second_half_end(self, mock_get):
        """종료월이 7월 이상이면 endPrdDe 는 하반기 코드(XX02)."""
        mock_response = MagicMock()
        mock_response.json.return_value = RAW_WAGE_SAMPLE
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        # start=202101(1월 → 202101), end=202208(8월 → 202202)
        self.svc.get_wage('202101', '202208')

        call_params = mock_get.call_args[1]['params']
        self.assertEqual(call_params['startPrdDe'], '202101')   # 상반기 2021
        self.assertEqual(call_params['endPrdDe'],   '202202')   # 하반기 2022

    @patch('apps.esc_calculator.services.kosis_service.requests.get')
    def test_ppi_fetches_only_missing_months_from_persistent_cache(self, mock_get):
        KosisCache.objects.create(
            data_type=KosisCache.DATA_TYPE_PPI,
            period_start='202107',
            period_end='202108',
            payload=[
                {'시점': '202107', '공산품': 111.81},
                {'시점': '202108', '공산품': 112.50},
            ],
        )

        mock_response = MagicMock()
        mock_response.json.return_value = [
            {'PRD_DE': '202109', 'C1_NM': '공산품', 'DT': '113.00'},
            {'PRD_DE': '202110', 'C1_NM': '공산품', 'DT': '114.00'},
        ]
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        result = self.svc.get_ppi('202107', '202110')

        call_params = mock_get.call_args[1]['params']
        self.assertEqual(call_params['startPrdDe'], '202109')
        self.assertEqual(call_params['endPrdDe'], '202110')
        self.assertEqual([r['시점'] for r in result], ['202107', '202108', '202109', '202110'])

    @patch('apps.esc_calculator.services.kosis_service.requests.get')
    def test_wage_fetches_only_missing_half_from_persistent_cache(self, mock_get):
        KosisCache.objects.create(
            data_type=KosisCache.DATA_TYPE_WAGE,
            period_start='202107',
            period_end='202206',
            payload=[
                {'시점': '202102', '값': 183500},
                {'시점': '202201', '값': 190000},
            ],
        )

        mock_response = MagicMock()
        mock_response.json.return_value = [
            {'PRD_DE': '202202', 'C1_NM': '일반공사', 'DT': '195000'},
        ]
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        result = self.svc.get_wage('202107', '202208')

        call_params = mock_get.call_args[1]['params']
        self.assertEqual(call_params['startPrdDe'], '202202')
        self.assertEqual(call_params['endPrdDe'], '202202')
        self.assertEqual([r['시점'] for r in result], ['202102', '202201', '202202'])
# ---------------------------------------------------------------------------
# EscProject CRUD API 테스트
# ---------------------------------------------------------------------------

class TestEscProjectAPI(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='pass1234!')
        self.other = User.objects.create_user(username='other', password='pass1234!')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _url(self, pk=None):
        base = '/api/esc/projects/'
        return f'{base}{pk}/' if pk else base

    def test_create_project(self):
        resp = self.client.post(self._url(), {
            'name': '테스트 프로젝트',
            'input_data': {'baseMonth': '202107', 'endMonth': '202203'},
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(EscProject.objects.count(), 1)
        self.assertEqual(EscProject.objects.first().user, self.user)

    def test_list_returns_only_own_projects(self):
        EscProject.objects.create(user=self.user, name='내것', input_data={})
        EscProject.objects.create(user=self.other, name='남의것', input_data={})
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        names = [p['name'] for p in resp.data['results'] if 'results' in resp.data] or [p['name'] for p in resp.data]
        self.assertEqual(len(names), 1)
        self.assertIn('내것', names)

    def test_retrieve_own_project(self):
        proj = EscProject.objects.create(user=self.user, name='P1', input_data={})
        resp = self.client.get(self._url(proj.pk))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_cannot_access_other_users_project(self):
        proj = EscProject.objects.create(user=self.other, name='남의것', input_data={})
        resp = self.client.get(self._url(proj.pk))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_update_project(self):
        proj = EscProject.objects.create(user=self.user, name='원본', input_data={})
        resp = self.client.patch(self._url(proj.pk), {'name': '수정됨'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        proj.refresh_from_db()
        self.assertEqual(proj.name, '수정됨')

    def test_delete_project(self):
        proj = EscProject.objects.create(user=self.user, name='삭제대상', input_data={})
        resp = self.client.delete(self._url(proj.pk))
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(EscProject.objects.count(), 0)

    def test_unauthenticated_is_rejected(self):
        anon = APIClient()
        resp = anon.get(self._url())
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


# ---------------------------------------------------------------------------
# KOSIS Proxy API 테스트
# ---------------------------------------------------------------------------

class TestKosisProxyAPI(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='apiuser', password='pass1234!')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_ppi_missing_params_returns_400(self):
        resp = self.client.get('/api/esc/kosis/ppi/')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_wage_missing_params_returns_400(self):
        resp = self.client.get('/api/esc/kosis/wage/')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_ppi_cache_hit_returns_200(self):
        payload = [
            {'시점': '202107', '공산품': 111.81},
            {'시점': '202108', '공산품': 112.50},
        ]
        KosisCache.objects.create(
            data_type=KosisCache.DATA_TYPE_PPI,
            period_start='202107', period_end='202108',
            payload=payload,
        )
        resp = self.client.get('/api/esc/kosis/ppi/?start=202107&end=202108')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data, payload)

    def test_wage_cache_hit_returns_200(self):
        payload = [{'시점': '202102', '값': 178321}]
        KosisCache.objects.create(
            data_type=KosisCache.DATA_TYPE_WAGE,
            period_start='202107', period_end='202112',
            payload=payload,
        )
        resp = self.client.get('/api/esc/kosis/wage/?start=202107&end=202112')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data, payload)

    def test_cache_reset_defaults_to_wage_only(self):
        KosisCache.objects.create(
            data_type=KosisCache.DATA_TYPE_PPI,
            period_start='202107',
            period_end='202108',
            payload=[{'시점': '202107', '공산품': 111.81}],
        )
        KosisCache.objects.create(
            data_type=KosisCache.DATA_TYPE_WAGE,
            period_start='202107',
            period_end='202112',
            payload=[{'시점': '202102', '값': 178321}],
        )

        resp = self.client.post('/api/esc/kosis/cache/reset/', {}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['data_type'], 'wage')
        self.assertEqual(KosisCache.objects.filter(data_type=KosisCache.DATA_TYPE_WAGE).count(), 0)
        self.assertEqual(KosisCache.objects.filter(data_type=KosisCache.DATA_TYPE_PPI).count(), 1)

    def test_cache_reset_rejects_invalid_data_type(self):
        resp = self.client.post('/api/esc/kosis/cache/reset/', {'data_type': 'bad'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

