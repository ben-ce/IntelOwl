# Generated by Django 3.2.18 on 2023-03-01 14:15

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('analyzers_manager', '0004_datamigration'),
    ]

    operations = [
        migrations.AlterField(
            model_name='analyzerconfig',
            name='python_module',
            field=models.CharField(db_index=True, max_length=120),
        ),
        migrations.AddIndex(
            model_name='analyzerconfig',
            index=models.Index(fields=['python_module', 'disabled'], name='analyzers_m_python__3e6166_idx'),
        ),
    ]
