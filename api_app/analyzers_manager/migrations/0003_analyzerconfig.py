# Generated by Django 3.2.18 on 2023-02-22 13:53

from django.db import migrations, models

import api_app.core.models
import api_app.fields
import api_app.validators


class Migration(migrations.Migration):

    dependencies = [
        ('analyzers_manager', '0002_analyzerreport_parent_playbook'),
    ]

    operations = [
        migrations.CreateModel(
            name='AnalyzerConfig',
            fields=[
                ('name', models.CharField(max_length=50, primary_key=True, serialize=False, unique=True)),
                ('type', models.CharField(choices=[('file', 'File'), ('observable', 'Observable')], max_length=50)),
                ('python_module', models.CharField(max_length=120)),
                ('description', models.TextField()),
                ('disabled', models.BooleanField(default=False)),
                ('config', models.JSONField(default=api_app.core.models.config_default, validators=[api_app.validators.validate_config])),
                ('secrets', models.JSONField(blank=True, default=dict, validators=[api_app.validators.validate_secrets])),
                ('params', models.JSONField(blank=True, default=dict, validators=[api_app.validators.validate_params])),
                ('docker_based', models.BooleanField(default=False)),
                ('external_service', models.BooleanField(default=True)),
                ('leaks_info', models.BooleanField()),
                ('observable_supported', api_app.fields.ChoiceArrayField(base_field=models.CharField(choices=[('ip', 'Ip'), ('url', 'Url'), ('domain', 'Domain'), ('hash', 'Hash'), ('generic', 'Generic')], max_length=30), blank=True, default=list, size=None)),
                ('supported_filetypes', api_app.fields.ChoiceArrayField(
                    base_field=models.CharField(
                        choices=[('application/javascript', 'Javascript1'), ('application/x-javascript', 'Javascript2'), ('text/javascript', 'Javascript3'), ('application/x-vbscript', 'Vb Script'), ('text/x-ms-iqy', 'Iqy'), ('application/vnd.android.package-archive', 'Apk'), ('application/x-dex', 'Dex'), ('application/onenote', 'One Note'), ('android', 'Android'), ('application/zip', 'Zip1'), ('multipart/x-zip', 'Zip2'), ('application/java-archive', 'Java'), ('text/rtf', 'Rtf1'), ('application/rtf', 'Rtf2'), ('application/x-dosexec', 'Dos'), ('application/x-sharedlib', 'Shared Lib'), ('application/x-executable', 'Exe'), ('application/x-elf', 'Elf'), ('application/octet-stream', 'Octet'), ('application/vnd.tcpdump.pcap', 'Pcap'), ('application/pdf', 'Pdf'), ('text/html', 'Html'), ('application/x-mspublisher', 'Pub'), ('application/vnd.ms-excel.addin.macroEnabled', 'Excel Macro1'), ('application/vnd.ms-excel.sheet.macroEnabled.12', 'Excel Macro2'), ('application/vnd.ms-excel', 'Excel1'), ('application/excel', 'Excel2'), ('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'Doc'), ('application/xml', 'Xml1'), ('text/xml', 'Xml2'), ('application/encrypted', 'Encrypted'), ('text/plain', 'Plain'), ('text/csv', 'Csv'), ('application/vnd.openxmlformats-officedocument.presentationml.presentation', 'Pptx'), ('application/msword', 'Word1'), ('application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'Word2'), ('application/vnd.ms-powerpoint', 'Powerpoint'), ('application/vnd.ms-office', 'Office'), ('application/x-binary', 'Binary'), ('application/x-macbinary', 'Mac1'), ('application/mac-binary', 'Mac2'), ('application/x-zip-compressed', 'Compress1'), ('application/x-compressed', 'Compress2')],
                        max_length=90), blank=True, default=list, size=None)),
                ('run_hash', models.BooleanField(default=False)),
                ('run_hash_type', models.CharField(blank=True, choices=[('md5', 'Md5'), ('sha256', 'Sha256')], max_length=10)),
                ('not_supported_filetypes', api_app.fields.ChoiceArrayField(base_field=models.CharField(choices=[('application/javascript', 'Javascript1'), ('application/x-javascript', 'Javascript2'), ('text/javascript', 'Javascript3'), ('application/x-vbscript', 'Vb Script'), ('text/x-ms-iqy', 'Iqy'), ('application/vnd.android.package-archive', 'Apk'), ('application/x-dex', 'Dex'), ('application/onenote', 'One Note'), ('android', 'Android'), ('application/zip', 'Zip1'), ('multipart/x-zip', 'Zip2'), ('application/java-archive', 'Java'), ('text/rtf', 'Rtf1'), ('application/rtf', 'Rtf2'), ('application/x-dosexec', 'Dos'), ('application/x-sharedlib', 'Shared Lib'), ('application/x-executable', 'Exe'), ('application/x-elf', 'Elf'), ('application/octet-stream', 'Octet'), ('application/vnd.tcpdump.pcap', 'Pcap'), ('application/pdf', 'Pdf'), ('text/html', 'Html'), ('application/x-mspublisher', 'Pub'), ('application/vnd.ms-excel.addin.macroEnabled', 'Excel Macro1'), ('application/vnd.ms-excel.sheet.macroEnabled.12', 'Excel Macro2'), ('application/vnd.ms-excel', 'Excel1'), ('application/excel', 'Excel2'), ('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'Doc'), ('application/xml', 'Xml1'), ('text/xml', 'Xml2'), ('application/encrypted', 'Encrypted'), ('text/plain', 'Plain'), ('text/csv', 'Csv'), ('application/vnd.openxmlformats-officedocument.presentationml.presentation', 'Pptx'), ('application/msword', 'Word1'), ('application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'Word2'), ('application/vnd.ms-powerpoint', 'Powerpoint'), ('application/vnd.ms-office', 'Office'), ('application/x-binary', 'Binary'), ('application/x-macbinary', 'Mac1'), ('application/mac-binary', 'Mac2'), ('application/x-zip-compressed', 'Compress1'), ('application/x-compressed', 'Compress2')], max_length=90), blank=True, default=list, size=None)),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
