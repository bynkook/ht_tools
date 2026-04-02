from django.contrib import admin

from .models import ConversionJob


@admin.register(ConversionJob)
class ConversionJobAdmin(admin.ModelAdmin):
    list_display = ['id', 'original_filename', 'category_name', 'status', 'created_at']
    list_filter = ['status', 'category_name']
    search_fields = ['original_filename']
    readonly_fields = ['callback_token', 'created_at']
    ordering = ['-created_at']
