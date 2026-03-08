"""
데이터 마이그레이션: image_inspector 기본 비교 알고리즘 설정 추가

기존 UserSettings의 preferences.image_inspector에 alignment_algorithm 필드가
없는 경우 기본값을 병합한다.
"""

from django.db import migrations

ALIGNMENT_DEFAULTS = {
    "alignment_algorithm": "orb",
}


def add_alignment_defaults(apps, schema_editor):
    UserSettings = apps.get_model('user_settings', 'UserSettings')
    for settings in UserSettings.objects.all():
        prefs = settings.preferences or {}
        image_inspector = prefs.get('image_inspector', {})
        changed = False
        for key, default_val in ALIGNMENT_DEFAULTS.items():
            if key not in image_inspector:
                image_inspector[key] = default_val
                changed = True
        if changed:
            prefs['image_inspector'] = image_inspector
            settings.preferences = prefs
            settings.save(update_fields=['preferences'])


def remove_alignment_defaults(apps, schema_editor):
    UserSettings = apps.get_model('user_settings', 'UserSettings')
    for settings in UserSettings.objects.all():
        prefs = settings.preferences or {}
        image_inspector = prefs.get('image_inspector', {})
        changed = False
        for key in ALIGNMENT_DEFAULTS:
            if key in image_inspector:
                del image_inspector[key]
                changed = True
        if changed:
            prefs['image_inspector'] = image_inspector
            settings.preferences = prefs
            settings.save(update_fields=['preferences'])


class Migration(migrations.Migration):

    dependencies = [
        ('user_settings', '0002_add_image_quality_settings'),
    ]

    operations = [
        migrations.RunPython(
            add_alignment_defaults,
            reverse_code=remove_alignment_defaults,
        ),
    ]
