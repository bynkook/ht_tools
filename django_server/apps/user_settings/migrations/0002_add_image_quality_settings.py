"""
데이터 마이그레이션: image_inspector 품질 설정 기본값 추가

기존 UserSettings의 preferences.image_inspector에 품질 설정 필드가
없는 경우 기본값을 병합한다. 기존 색상 설정은 유지된다.
"""

from django.db import migrations

QUALITY_DEFAULTS = {
    "output_quality": 85,
    "output_resolution": 2000,
    "processing_resolution": 6000,
    "pdf_dpi": 200,
}


def add_quality_defaults(apps, schema_editor):
    UserSettings = apps.get_model('user_settings', 'UserSettings')
    updated_count = 0
    for settings in UserSettings.objects.all():
        prefs = settings.preferences or {}
        img = prefs.get('image_inspector', {})
        changed = False
        for key, default_val in QUALITY_DEFAULTS.items():
            if key not in img:
                img[key] = default_val
                changed = True
        if changed:
            prefs['image_inspector'] = img
            settings.preferences = prefs
            settings.save(update_fields=['preferences'])
            updated_count += 1


def remove_quality_defaults(apps, schema_editor):
    """롤백: 품질 설정 필드 제거"""
    UserSettings = apps.get_model('user_settings', 'UserSettings')
    for settings in UserSettings.objects.all():
        prefs = settings.preferences or {}
        img = prefs.get('image_inspector', {})
        changed = False
        for key in QUALITY_DEFAULTS:
            if key in img:
                del img[key]
                changed = True
        if changed:
            prefs['image_inspector'] = img
            settings.preferences = prefs
            settings.save(update_fields=['preferences'])


class Migration(migrations.Migration):

    dependencies = [
        ('user_settings', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(
            add_quality_defaults,
            reverse_code=remove_quality_defaults,
        ),
    ]
