import logging
import datetime

from django.contrib.admin.views.decorators import staff_member_required
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView
from django.utils import timezone
from django.contrib.auth.models import User
from django.db.models import Count, Sum, Q
from django.db.models.functions import Length

logger = logging.getLogger(__name__)


@method_decorator(staff_member_required, name='dispatch')
class UsageStatsView(TemplateView):
    template_name = 'admin/usage_stats.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        now = timezone.now()
        week_ago = now - datetime.timedelta(days=7)
        month_ago = now - datetime.timedelta(days=30)

        users = list(User.objects.filter(is_active=True).order_by('username'))

        # ── 채팅 통계 사전 집계 (JOIN 중복 방지를 위해 앱별 분리) ──────────────
        try:
            # FabriX Chat  (related: user → model_chat_sessions → messages)
            from apps.fabrix_chat.models import ChatMessage as FabriXMsg

            _fc_week = (
                FabriXMsg.objects
                .filter(created_at__gte=week_ago)
                .values('session__user_id')
                .annotate(cnt=Count('id'), bytes=Sum(Length('content')))
            )
            fc_week = {r['session__user_id']: r for r in _fc_week}

            _fc_month = (
                FabriXMsg.objects
                .filter(created_at__gte=month_ago)
                .values('session__user_id')
                .annotate(cnt=Count('id'), bytes=Sum(Length('content')))
            )
            fc_month = {r['session__user_id']: r for r in _fc_month}

        except Exception as e:
            logger.error(f"[UsageStats] FabriX Chat 집계 오류: {e}")
            fc_week = fc_month = {}

        try:
            # Agent Chat  (related: user → sessions → messages)
            from apps.fabrix_agent_chat.models import ChatMessage as AgentMsg

            _ac_week = (
                AgentMsg.objects
                .filter(created_at__gte=week_ago)
                .values('session__user_id')
                .annotate(cnt=Count('id'), bytes=Sum(Length('content')))
            )
            ac_week = {r['session__user_id']: r for r in _ac_week}

            _ac_month = (
                AgentMsg.objects
                .filter(created_at__gte=month_ago)
                .values('session__user_id')
                .annotate(cnt=Count('id'), bytes=Sum(Length('content')))
            )
            ac_month = {r['session__user_id']: r for r in _ac_month}

        except Exception as e:
            logger.error(f"[UsageStats] Agent Chat 집계 오류: {e}")
            ac_week = ac_month = {}

        # ── Data Explorer 이용 횟수 집계 ─────────────────────────────────────
        try:
            from apps.core.models import AppUsageLog

            _de_week = (
                AppUsageLog.objects
                .filter(app='data_explorer', created_at__gte=week_ago)
                .values('user_id')
                .annotate(cnt=Count('id'))
            )
            de_week = {r['user_id']: r['cnt'] for r in _de_week}

            _de_month = (
                AppUsageLog.objects
                .filter(app='data_explorer', created_at__gte=month_ago)
                .values('user_id')
                .annotate(cnt=Count('id'))
            )
            de_month = {r['user_id']: r['cnt'] for r in _de_month}

        except Exception as e:
            logger.error(f"[UsageStats] Data Explorer 집계 오류: {e}")
            de_week = de_month = {}

        # ── 사용자별 통계 조합 ───────────────────────────────────────────────
        stats = []
        # Total Sum 집계
        totals = {
            'fc_week_cnt': 0, 'fc_week_bytes': 0,
            'fc_month_cnt': 0, 'fc_month_bytes': 0,
            'ac_week_cnt': 0, 'ac_week_bytes': 0,
            'ac_month_cnt': 0, 'ac_month_bytes': 0,
            'de_week_cnt': 0, 'de_month_cnt': 0,
        }

        for user in users:
            uid = user.pk
            row = {
                'username':        user.username,
                'email':           user.email,
                'is_staff':        user.is_staff,
                # FabriX Chat
                'fc_week_cnt':     fc_week.get(uid, {}).get('cnt', 0) or 0,
                'fc_week_bytes':   fc_week.get(uid, {}).get('bytes', 0) or 0,
                'fc_month_cnt':    fc_month.get(uid, {}).get('cnt', 0) or 0,
                'fc_month_bytes':  fc_month.get(uid, {}).get('bytes', 0) or 0,
                # Agent Chat
                'ac_week_cnt':     ac_week.get(uid, {}).get('cnt', 0) or 0,
                'ac_week_bytes':   ac_week.get(uid, {}).get('bytes', 0) or 0,
                'ac_month_cnt':    ac_month.get(uid, {}).get('cnt', 0) or 0,
                'ac_month_bytes':  ac_month.get(uid, {}).get('bytes', 0) or 0,
                # Data Explorer
                'de_week_cnt':     de_week.get(uid, 0),
                'de_month_cnt':    de_month.get(uid, 0),
            }
            stats.append(row)

            # Accumulate totals
            totals['fc_week_cnt'] += row['fc_week_cnt']
            totals['fc_week_bytes'] += row['fc_week_bytes']
            totals['fc_month_cnt'] += row['fc_month_cnt']
            totals['fc_month_bytes'] += row['fc_month_bytes']
            totals['ac_week_cnt'] += row['ac_week_cnt']
            totals['ac_week_bytes'] += row['ac_week_bytes']
            totals['ac_month_cnt'] += row['ac_month_cnt']
            totals['ac_month_bytes'] += row['ac_month_bytes']
            totals['de_week_cnt'] += row['de_week_cnt']
            totals['de_month_cnt'] += row['de_month_cnt']

        context.update({
            'title':        '사용자별 이용량 통계',
            'stats':        stats,
            'period_week':  week_ago.strftime('%Y-%m-%d'),
            'period_month': month_ago.strftime('%Y-%m-%d'),
            'now':          now.strftime('%Y-%m-%d %H:%M'),
            # Total values
            'total_fc_week_cnt':     totals['fc_week_cnt'],
            'total_fc_week_bytes':   totals['fc_week_bytes'],
            'total_fc_month_cnt':    totals['fc_month_cnt'],
            'total_fc_month_bytes':  totals['fc_month_bytes'],
            'total_ac_week_cnt':     totals['ac_week_cnt'],
            'total_ac_week_bytes':   totals['ac_week_bytes'],
            'total_ac_month_cnt':    totals['ac_month_cnt'],
            'total_ac_month_bytes':  totals['ac_month_bytes'],
            'total_de_week_cnt':     totals['de_week_cnt'],
            'total_de_month_cnt':    totals['de_month_cnt'],
        })
        return context
