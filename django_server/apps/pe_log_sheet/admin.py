from django.contrib import admin
from django.contrib import messages
from .models import PeLogSheetState, PeLogSheetRevision


@admin.register(PeLogSheetState)
class PeLogSheetStateAdmin(admin.ModelAdmin):
    list_display = ('singleton_key', 'revision', 'last_editor', 'updated_at')
    readonly_fields = ('singleton_key', 'initialized_at', 'updated_at')
    list_filter = ('last_editor',)

    def has_add_permission(self, request):
        # Singleton - don't allow adding via admin
        return False

    actions = ['reset_from_seed', 'clear_all_history']

    @admin.action(description='시트 초기화 (seed.csv 로드, 히스토리 삭제)')
    def reset_from_seed(self, request, queryset):
        from .services.csv_loader import csv_to_workbook, normalize_workbook_data
        import os
        from django.conf import settings

        csv_path = os.path.join(settings.ROOT_DIR, 'data', 'pe_log', 'seed.csv')
        if os.path.exists(csv_path):
            workbook_data = normalize_workbook_data(csv_to_workbook(csv_path))
            msg = f'seed.csv에서 로드 완료'
        else:
            from .services.csv_loader import DEFAULT_HEADERS, _build_workbook_from_rows
            workbook_data = normalize_workbook_data(_build_workbook_from_rows(DEFAULT_HEADERS, []))
            msg = f'빈 시트로 초기화 (seed.csv 없음)'

        for state in queryset:
            # 히스토리도 같이 삭제
            state.revisions.all().delete()
            state.workbook_data = workbook_data
            state.revision = 0  # 리비전을 0으로 리셋
            state.source_checksum = ''
            state.save()

        self.message_user(request, f'{queryset.count()}개 시트 초기화됨. {msg}. ※ 브라우저 새로고침 필요', messages.SUCCESS)

    @admin.action(description='히스토리만 삭제 (시트 데이터 유지)')
    def clear_all_history(self, request, queryset):
        total = 0
        for state in queryset:
            count = state.revisions.all().delete()[0]
            total += count
        self.message_user(request, f'{total}개 히스토리 레코드 삭제됨', messages.SUCCESS)


@admin.register(PeLogSheetRevision)
class PeLogSheetRevisionAdmin(admin.ModelAdmin):
    list_display = ('id', 'document', 'base_revision', 'new_revision', 'editor', 'created_at')
    list_filter = ('editor', 'created_at')
    readonly_fields = ('document', 'base_revision', 'new_revision', 'ops', 'editor', 'created_at')
    ordering = ('-created_at',)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
