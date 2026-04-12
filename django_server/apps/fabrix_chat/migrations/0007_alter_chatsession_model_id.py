from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fabrix_chat', '0006_chatmessage_metadata'),
    ]

    operations = [
        migrations.AlterField(
            model_name='chatsession',
            name='model_id',
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text='FabriX Model UUID',
                max_length=100,
                null=True,
            ),
        ),
    ]
