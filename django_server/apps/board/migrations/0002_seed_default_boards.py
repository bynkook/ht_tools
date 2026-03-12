from django.db import migrations


DEFAULT_BOARDS = [
    {
        'name': 'dashboardList',
        'slug': 'dashboard-list',
        'title_display': 'Dashboard List',
        'description': '대시보드 링크와 자료를 관리하는 기본 게시판입니다.',
        'is_active': True,
        'allow_create': True,
        'allow_update': True,
        'allow_delete': True,
    },
]


def seed_default_boards(apps, schema_editor):
    Board = apps.get_model('board', 'Board')
    for board in DEFAULT_BOARDS:
        Board.objects.get_or_create(
            name=board['name'],
            defaults={
                'slug': board['slug'],
                'title_display': board['title_display'],
                'description': board['description'],
                'is_active': board['is_active'],
                'allow_create': board['allow_create'],
                'allow_update': board['allow_update'],
                'allow_delete': board['allow_delete'],
            },
        )


def remove_default_boards(apps, schema_editor):
    Board = apps.get_model('board', 'Board')
    Board.objects.filter(name__in=[board['name'] for board in DEFAULT_BOARDS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('board', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_default_boards, remove_default_boards),
    ]