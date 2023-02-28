# This file is a part of IntelOwl https://github.com/intelowlproject/IntelOwl
# See the file 'LICENSE' for copying permission.
import copy
import json
import logging
from typing import Dict, List

from django.db.models import Q
from django.http import QueryDict
from drf_spectacular.utils import extend_schema_serializer
from durin.serializers import UserSerializer
from rest_framework import serializers as rfs
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.fields import empty

from certego_saas.apps.organization.membership import Membership

# from django.contrib.auth import get_user_model
from certego_saas.apps.organization.organization import Organization
from certego_saas.apps.organization.permissions import IsObjectOwnerOrSameOrgPermission

from .analyzers_manager.constants import ObservableTypes, TypeChoices
from .analyzers_manager.exceptions import NotRunnableAnalyzer
from .analyzers_manager.models import AnalyzerConfig, MimeTypes
from .analyzers_manager.serializers import AnalyzerReportSerializer
from .connectors_manager.exceptions import NotRunnableConnector
from .connectors_manager.models import ConnectorConfig
from .connectors_manager.serializers import ConnectorReportSerializer
from .helpers import calculate_md5, gen_random_colorhex
from .models import TLP, Job, PluginConfig, Tag
from .playbooks_manager.exceptions import NotRunnablePlaybook
from .playbooks_manager.models import PlaybookConfig
from .visualizers_manager.models import VisualizerConfig
from .visualizers_manager.serializers import VisualizerReportSerializer

logger = logging.getLogger(__name__)

__all__ = [
    "TagSerializer",
    "JobAvailabilitySerializer",
    "JobListSerializer",
    "JobSerializer",
    "FileAnalysisSerializer",
    "ObservableAnalysisSerializer",
    "AnalysisResponseSerializer",
    "MultipleFileAnalysisSerializer",
    "MultipleObservableAnalysisSerializer",
    "multi_result_enveloper",
    "PluginConfigSerializer",
    "PlaybookFileAnalysisSerializer",
    "PlaybookObservableAnalysisSerializer",
]


# User = get_user_model()


class TagSerializer(rfs.ModelSerializer):
    class Meta:
        model = Tag
        fields = rfs.ALL_FIELDS


class JobAvailabilitySerializer(rfs.ModelSerializer):
    """
    Serializer for ask_analysis_availability
    """

    class Meta:
        model = Job
        fields = rfs.ALL_FIELDS

    md5 = rfs.CharField(max_length=128, required=True)
    analyzers = rfs.ListField(default=list)
    playbooks = rfs.ListField(default=list, required=False)
    running_only = rfs.BooleanField(default=False, required=False)
    minutes_ago = rfs.IntegerField(default=None, required=False)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        playbooks = attrs.get("playbooks", [])
        analyzers = attrs.get("analyzers", [])

        if len(playbooks) != 0 and len(analyzers) != 0:
            raise rfs.ValidationError(
                "Either only send the 'playbooks' parameter or the 'analyzers' one."
            )
        return attrs


class _AbstractJobViewSerializer(rfs.ModelSerializer):
    """
    Base Serializer for ``Job`` model's ``retrieve()`` and ``list()``.
    """

    user = UserSerializer()
    tags = TagSerializer(many=True, read_only=True)


class _AbstractJobCreateSerializer(rfs.ModelSerializer):
    """
    Base Serializer for ``Job`` model's ``create()``.
    """

    tags_labels = rfs.ListField(default=list)
    runtime_configuration = rfs.JSONField(required=False, default={}, write_only=True)
    analyzers_requested = rfs.ListField(default=list)
    connectors_requested = rfs.ListField(default=list)
    md5 = rfs.HiddenField(default=None)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.filter_warnings = []
        self.log_runnable = True

    def validate(self, attrs: dict) -> dict:
        # check and validate runtime_configuration
        self.filter_analyzers_and_connectors(attrs)
        return attrs

    def filter_visualizers(self, serialized_data: Dict) -> List[str]:
        visualizers_to_execute = []

        for visualizer in VisualizerConfig.objects.all():
            visualizer: VisualizerConfig
            if (
                visualizer.is_runnable(self.context["request"].user)
                # subsets
                and set(visualizer.analyzers.all().values_list("pk", flat=True))
                <= set(
                    AnalyzerConfig.objects.filter(
                        name__in=serialized_data["analyzers_to_execute"]
                    ).values_list("pk", flat=True)
                )
                and set(visualizer.connectors.all().values_list("pk", flat=True))
                <= set(
                    ConnectorConfig.objects.filter(
                        name__in=serialized_data["analyzers_to_execute"]
                    ).values_list("pk", flat=True)
                )
            ):
                logger.info(f"Going to use {visualizer.name}")
                visualizers_to_execute.append(visualizer.name)
        return visualizers_to_execute

    def filter_analyzers(self, serialized_data: Dict) -> List[str]:
        # init empty list
        cleaned_analyzer_list = []

        analyzers_requested = serialized_data.get("analyzers_requested", [])
        if not analyzers_requested:
            analyzers_requested = list(
                AnalyzerConfig.objects.all().values_list("name", flat=True)
            )
            serialized_data["analyzers_requested"] = analyzers_requested
            self.run_all_analyzers = True
        else:
            self.run_all_analyzers = False
        tlp = serialized_data.get("tlp", TLP.WHITE).upper()

        for a_name in analyzers_requested:
            try:
                try:
                    config = AnalyzerConfig.objects.get(name=a_name)
                except AnalyzerConfig.DoesNotExist:
                    if not self.run_all_analyzers:
                        raise NotRunnableAnalyzer(
                            f"{a_name} won't run: not available in configuration"
                        )
                    # don't add warning if self.run_all_analyzers
                    continue
                config: AnalyzerConfig
                if not config.is_runnable(self.context["request"].user):
                    raise NotRunnableAnalyzer(
                        f"{a_name} won't run: is disabled or unconfigured"
                    )

                if tlp != TLP.WHITE and config.leaks_info:
                    raise NotRunnableAnalyzer(
                        f"{a_name} won't be run because it leaks info externally."
                    )
                if tlp == TLP.RED and config.external_service:
                    raise NotRunnableAnalyzer(
                        f"{a_name} won't be run because you"
                        " filtered external analyzers."
                    )
            except NotRunnableAnalyzer as e:
                if not self.log_runnable:
                    # in this case, they are not warnings but
                    # expected and wanted behavior
                    logger.debug(e)
                else:
                    logger.warning(e)
                    self.filter_warnings.append(str(e))
            else:
                cleaned_analyzer_list.append(a_name)

        if not cleaned_analyzer_list:
            raise ValidationError(
                {"detail": "No Analyzers can be run after filtering."}
            )
        return cleaned_analyzer_list

    def filter_connectors(self, serialized_data: Dict) -> List[str]:
        # init empty list
        cleaned_connectors_list = []

        connectors_requested = serialized_data.get("connectors_requested", [])
        if not connectors_requested:
            connectors_requested = list(
                ConnectorConfig.objects.all().values_list("name", flat=True)
            )
            serialized_data["connectors_requested"] = connectors_requested
            self.run_all_connectors = True
        else:
            self.run_all_connectors = False

        tlp = serialized_data.get("tlp", TLP.WHITE).upper()

        for c_name in connectors_requested:
            try:
                try:
                    config = ConnectorConfig.objects.get(name=c_name)
                except ConnectorConfig.DoesNotExist:
                    if not self.run_all_connectors:
                        raise NotRunnableConnector(
                            f"{c_name} won't run: not available in configuration"
                        )
                    # don't add warning if self.run_all_connectors
                    continue
                config: ConnectorConfig
                if not config.is_runnable(self.context["request"].user):
                    raise NotRunnableConnector(
                        f"{c_name} won't run: is disabled or unconfigured"
                    )

                if TLP.get_priority(tlp) > TLP.get_priority(
                    config.maximum_tlp
                ):  # check if job's tlp allows running
                    # e.g. if connector_tlp is GREEN(1),
                    # run for job_tlp WHITE(0) & GREEN(1) only
                    raise NotRunnableConnector(
                        f"{c_name} won't run: "
                        f"job.tlp ('{tlp}') > maximum_tlp ('{config.maximum_tlp}')"
                    )
            except NotRunnableConnector as e:
                logger.warning(e)
                self.filter_warnings.append(str(e))
            else:
                cleaned_connectors_list.append(c_name)

        return cleaned_connectors_list

    def filter_analyzers_and_connectors(self, attrs: dict) -> dict:
        attrs["analyzers_to_execute"] = self.filter_analyzers(attrs)
        attrs["connectors_to_execute"] = self.filter_connectors(attrs)
        attrs["visualizers_to_execute"] = self.filter_visualizers(attrs)
        attrs["warnings"] = self.filter_warnings
        return attrs

    def create(self, validated_data: dict) -> Job:
        # create ``Tag`` objects from tags_labels
        tags_labels = validated_data.pop("tags_labels", None)
        validated_data.pop("warnings")
        validated_data.pop("runtime_configuration")
        tags = [
            Tag.objects.get_or_create(
                label=label, defaults={"color": gen_random_colorhex()}
            )[0]
            for label in tags_labels
        ]

        job = Job.objects.create(**validated_data)
        if tags:
            job.tags.set(tags)

        return job


class JobListSerializer(_AbstractJobViewSerializer):
    """
    Used for ``list()``.
    """

    class Meta:
        model = Job
        exclude = ("file",)


class JobSerializer(_AbstractJobViewSerializer):
    """
    Used for ``retrieve()``
    """

    class Meta:
        model = Job
        exclude = ("file",)

    analyzer_reports = AnalyzerReportSerializer(many=True, read_only=True)
    connector_reports = ConnectorReportSerializer(many=True, read_only=True)
    visualizer_reports = VisualizerReportSerializer(many=True, read_only=True)

    permissions = rfs.SerializerMethodField()

    def get_permissions(self, obj: Job) -> Dict[str, bool]:
        request = self.context.get("request", None)
        view = self.context.get("view", None)
        if request and view:
            has_perm = IsObjectOwnerOrSameOrgPermission().has_object_permission(
                request, view, obj
            )
            return {
                "kill": has_perm,
                "delete": has_perm,
                "plugin_actions": has_perm,
            }
        return {}


class MultipleFileAnalysisSerializer(rfs.ListSerializer):
    """
    ``Job`` model's serializer for Multiple File Analysis.
    Used for ``create()``.
    """

    def update(self, instance, validated_data):
        raise NotImplementedError("This serializer does not support update().")

    files = rfs.ListField(child=rfs.FileField(required=True), required=True)

    file_names = rfs.ListField(child=rfs.CharField(required=True), required=True)

    file_mimetypes = rfs.ListField(
        child=rfs.CharField(required=True, allow_blank=True), required=False
    )

    def to_internal_value(self, data: QueryDict):
        ret = []
        errors = []

        if data.getlist("file_names", False) and len(data.getlist("file_names")) != len(
            data.getlist("files")
        ):
            raise ValidationError("file_names and files must have the same length.")

        try:
            base_data: QueryDict = data.copy()
        except TypeError:  # https://code.djangoproject.com/ticket/29510
            base_data: QueryDict = QueryDict(mutable=True)
            for key, value_list in data.lists():
                if key not in ["files", "file_names", "file_mimetypes"]:
                    base_data.setlist(key, copy.deepcopy(value_list))

        for index, file in enumerate(data.getlist("files")):
            # `deepcopy` here ensures that this code doesn't
            # break even if new fields are added in future
            item = base_data.copy()

            item["file"] = file
            if data.getlist("file_names", False):
                item["file_name"] = data.getlist("file_names")[index]
            if data.get("file_mimetypes", False):
                item["file_mimetype"] = data["file_mimetypes"][index]
            try:
                validated = self.child.run_validation(item)
            except ValidationError as exc:
                errors.append(exc.detail)
            else:
                ret.append(validated)
                errors.append({})

        if any(errors):
            raise ValidationError(errors)

        return ret


class FileAnalysisSerializer(_AbstractJobCreateSerializer):
    """
    ``Job`` model's serializer for File Analysis.
    Used for ``create()``.
    """

    file = rfs.FileField(required=True)
    file_name = rfs.CharField(required=False)
    file_mimetype = rfs.CharField(required=False)

    class Meta:
        model = Job
        fields = (
            "id",
            "user",
            "is_sample",
            "md5",
            "tlp",
            "file",
            "file_name",
            "file_mimetype",
            "runtime_configuration",
            "analyzers_requested",
            "connectors_requested",
            "tags_labels",
        )
        list_serializer_class = MultipleFileAnalysisSerializer

    def validate(self, attrs: dict) -> dict:
        logger.debug(f"before attrs: {attrs}")
        # calculate ``file_mimetype``
        if "file_name" not in attrs:
            attrs["file_name"] = attrs["file"].name
        try:
            attrs["file_mimetype"] = MimeTypes.calculate(
                attrs["file"], attrs["file_name"]
            )
        except ValueError as e:
            raise ValidationError(e)
        # calculate ``md5``
        file_obj = attrs["file"].file
        file_obj.seek(0)
        file_buffer = file_obj.read()
        attrs["md5"] = calculate_md5(file_buffer)
        attrs = super().validate(attrs)
        logger.debug(f"after attrs: {attrs}")
        return attrs

    def filter_analyzers(self, serialized_data: Dict) -> List[str]:
        cleaned_analyzer_list = []

        # get values from serializer
        partially_filtered_analyzers = super().filter_analyzers(serialized_data)
        for a_name in partially_filtered_analyzers:
            try:
                # at this point we are sure that the analyzer object is present,
                # but not its type
                file_mimetype = serialized_data["file_mimetype"]

                supported_query = Q(
                    supported_filetypes__isnull=True,
                    not_supported_filetypes__not__contains=[file_mimetype],
                ) | Q(supported_filetypes__contains=[file_mimetype])
                try:
                    AnalyzerConfig.objects.get(
                        Q(name=a_name, type=TypeChoices.FILE) & supported_query
                    )
                except AnalyzerConfig.DoesNotExist:
                    raise NotRunnableAnalyzer(
                        f"{a_name} won't be run because"
                        " does not support the file mimetype."
                    )

            except NotRunnableAnalyzer as e:
                if not self.log_runnable:
                    # in this case, they are not warnings but
                    # expected and wanted behavior
                    logger.debug(e)
                else:
                    logger.warning(e)
                    self.filter_warnings.append(str(e))
            else:
                cleaned_analyzer_list.append(a_name)

        if not cleaned_analyzer_list:
            raise ValidationError(
                {"detail": "No Analyzers can be run after filtering."}
            )
        return cleaned_analyzer_list


class MultipleObservableAnalysisSerializer(rfs.ListSerializer):
    """
    ``Job`` model's serializer for Multiple Observable Analysis.
    Used for ``create()``.
    """

    def update(self, instance, validated_data):
        raise NotImplementedError("This serializer does not support update().")

    observables = rfs.ListField(required=True)

    def to_internal_value(self, data):
        ret = []
        errors = []

        for classification, name in data.pop("observables", []):

            # `deepcopy` here ensures that this code doesn't
            # break even if new fields are added in future
            item = copy.deepcopy(data)

            item["observable_name"] = name
            if classification:
                item["observable_classification"] = classification
            try:
                validated = self.child.run_validation(item)
            except ValidationError as exc:
                errors.append(exc.detail)
            else:
                ret.append(validated)
                errors.append({})

        if any(errors):
            raise ValidationError(errors)

        return ret


class ObservableAnalysisSerializer(_AbstractJobCreateSerializer):
    """
    ``Job`` model's serializer for Observable Analysis.
    Used for ``create()``.
    """

    observable_name = rfs.CharField(required=True)
    observable_classification = rfs.CharField(required=False)

    class Meta:
        model = Job
        fields = (
            "id",
            "user",
            "is_sample",
            "md5",
            "tlp",
            "observable_name",
            "observable_classification",
            "runtime_configuration",
            "analyzers_requested",
            "connectors_requested",
            "tags_labels",
        )
        list_serializer_class = MultipleObservableAnalysisSerializer

    def validate(self, attrs: dict) -> dict:
        logger.debug(f"before attrs: {attrs}")
        # calculate ``observable_classification``
        if not attrs.get("observable_classification", None):
            attrs["observable_classification"] = ObservableTypes.calculate(
                attrs["observable_name"]
            )
        attrs["observable_name"] = self.defanged_values_removal(
            attrs["observable_name"]
        )
        if attrs["observable_classification"] in [
            ObservableTypes.HASH,
            ObservableTypes.DOMAIN,
        ]:
            # force lowercase in ``observable_name``.
            # Ref: https://github.com/intelowlproject/IntelOwl/issues/658
            attrs["observable_name"] = attrs["observable_name"].lower()
        # calculate ``md5``
        attrs["md5"] = calculate_md5(attrs["observable_name"].encode("utf-8"))
        attrs = super().validate(attrs)
        logger.debug(f"after attrs: {attrs}")
        return attrs

    @staticmethod
    def defanged_values_removal(value):
        if "\\" in value:
            value = value.replace("\\", "")
        if "]" in value:
            value = value.replace("]", "")
        if "[" in value:
            value = value.replace("[", "")
        return value

    def filter_analyzers(self, serialized_data: Dict) -> List[str]:
        cleaned_analyzer_list = []

        # get values from serializer
        partially_filtered_analyzers = super().filter_analyzers(serialized_data)

        for a_name in partially_filtered_analyzers:
            try:
                # at this point we are sure that the analyzer object is present,
                # but not its type
                try:
                    AnalyzerConfig.objects.get(
                        name=a_name,
                        type=TypeChoices.OBSERVABLE,
                        observable_supported__contains=[
                            serialized_data["observable_classification"]
                        ],
                    )
                except AnalyzerConfig.DoesNotExist:
                    raise NotRunnableAnalyzer(
                        f"{a_name} won't be run because "
                        "it does not support the requested observable."
                    )
            except NotRunnableAnalyzer as e:
                if not self.log_runnable:
                    # in this case, they are not warnings but
                    # expected and wanted behavior
                    logger.debug(e)
                else:
                    logger.warning(e)
                    self.filter_warnings.append(str(e))
            else:
                cleaned_analyzer_list.append(a_name)

        if not cleaned_analyzer_list:
            raise ValidationError(
                {"detail": "No Analyzers can be run after filtering."}
            )
        return cleaned_analyzer_list


class PlaybookBaseSerializer:
    def filter_playbooks(self, attrs: Dict) -> Dict:
        # init empty list
        valid_playbook_list = []
        analyzers_requested = []
        connectors_requested = []
        runtime_configurations = []
        # get values from serializer
        selected_playbooks = attrs.get("playbooks_requested", [])

        # read config

        for p_name in selected_playbooks:
            try:
                pp = PlaybookConfig.objects.get(name=p_name)
                if not pp:
                    raise NotRunnablePlaybook(f"{p_name} does not exists")
                elif pp.disabled:
                    raise NotRunnablePlaybook(f"{p_name} won't run: disabled")
                else:
                    analyzers_requested.extend(
                        list(pp.analyzers.all().values_list("name", flat=True))
                    )
                    connectors_requested.extend(
                        list(pp.connectors.all().values_list("name", flat=True))
                    )
                    runtime_configurations.append(pp.runtime_configuration["analyzers"] | pp.runtime_configuration["connectors"])
                    valid_playbook_list.append(p_name)
            except NotRunnablePlaybook as e:
                logger.warning(e)
                self.filter_warnings.append(str(e))

        if not valid_playbook_list:
            raise ValidationError(
                {"detail": "No playbooks can be run after filtering."}
            )

        attrs["playbooks_to_execute"] = valid_playbook_list
        attrs["analyzers_requested"] = list(set(analyzers_requested))
        attrs["connectors_requested"] = list(set(connectors_requested))
        attrs["runtime_configuration"] = runtime_configurations

        return attrs


class PlaybookObservableAnalysisSerializer(
    PlaybookBaseSerializer, ObservableAnalysisSerializer
):
    class Meta:
        model = Job
        fields = (
            "id",
            "user",
            "is_sample",
            "md5",
            "tlp",
            "observable_name",
            "observable_classification",
            "runtime_configuration",
            "analyzers_requested",
            "connectors_requested",
            "playbooks_requested",
            "tags_labels",
        )
        list_serializer_class = MultipleObservableAnalysisSerializer

    def validate(self, attrs: dict) -> dict:
        attrs = self.filter_playbooks(attrs)
        # this is needed because we do not want to have warning on missmatch plugins
        self.log_runnable = False
        attrs = super().validate(attrs)

        return attrs


class PlaybookFileAnalysisSerializer(PlaybookBaseSerializer, FileAnalysisSerializer):
    class Meta:
        model = Job
        fields = (
            "id",
            "user",
            "is_sample",
            "md5",
            "tlp",
            "file",
            "file_name",
            "file_mimetype",
            "runtime_configuration",
            "analyzers_requested",
            "connectors_requested",
            "playbooks_requested",
            "tags_labels",
        )
        list_serializer_class = MultipleFileAnalysisSerializer

    def validate(self, attrs: dict) -> dict:
        attrs["observable_classification"] = "file"
        attrs = super().filter_playbooks(attrs)
        # this is needed because we do not want to have warning on missmatch plugins
        self.log_runnable = False
        attrs = super().validate(attrs)

        return attrs


class AnalysisResponseSerializer(rfs.Serializer):
    job_id = rfs.IntegerField()
    status = rfs.CharField()
    warnings = rfs.ListField(required=False)
    analyzers_running = rfs.ListField()
    connectors_running = rfs.ListField()
    visualizers_running = rfs.ListField()
    playbooks_running = rfs.ListField(required=False)


def multi_result_enveloper(serializer_class, many):
    component_name = (
        f'Multi{serializer_class.__name__.replace("Serializer", "")}'
        f'{"List" if many else ""}'
    )

    @extend_schema_serializer(many=False, component_name=component_name)
    class EnvelopeSerializer(rfs.Serializer):
        count = rfs.BooleanField()  # No. of items in the results list
        results = serializer_class(many=many)

    return EnvelopeSerializer


class PluginConfigSerializer(rfs.ModelSerializer):
    class Meta:
        model = PluginConfig
        fields = rfs.ALL_FIELDS

    class CustomJSONField(rfs.JSONField):
        def run_validation(self, data=empty):
            value = super().run_validation(data)
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                raise ValidationError("Value is not JSON-compliant.")

        def to_representation(self, value):
            return json.dumps(super().to_representation(value))

    # certego_saas does not expose organization.id to frontend
    organization = rfs.SlugRelatedField(
        allow_null=True,
        slug_field="name",
        queryset=Organization.objects.all(),
        required=False,
    )
    owner = rfs.HiddenField(default=rfs.CurrentUserDefault())
    value = CustomJSONField()

    def validate_type(self, _type: str):
        if _type == PluginConfig.PluginType.ANALYZER:
            self.config = AnalyzerConfig
            self.category = "Analyzer"
        elif _type == PluginConfig.PluginType.CONNECTOR:
            self.config = ConnectorConfig
            self.category = "Connector"
        elif _type == PluginConfig.PluginType.VISUALIZER:
            self.config = VisualizerConfig
            self.category = "Visualizer"
        else:
            logger.error(f"Unknown custom config type: {_type}")
            raise ValidationError("Invalid type.")
        return _type

    def to_representation(self, instance):
        if (
            instance.organization
            and self.context["request"].user.pk != instance.organization.owner.pk
        ):
            instance.value = "redacted"
        return super().to_representation(instance)

    def validate_organization(self, organization: str):
        # here the owner can't be retrieved by the field
        # because the HiddenField will always return None
        owner = self.context["request"].user
        # check if the user is owner of the organization
        membership = Membership.objects.filter(
            user=owner,
            organization=organization,
            is_owner=True,
        )
        if not membership.exists():
            logger.warning(
                f"User {owner} is not owner of " f"organization {organization}."
            )
            raise PermissionDenied("User is not owner of the organization.")
        return organization

    def validate(self, attrs):
        super().validate(attrs)
        try:
            config_obj = self.config.objects.get(name=attrs["plugin_name"])
        except self.config.DoesNotExist:
            raise ValidationError(
                f"{self.category} {attrs['plugin_name']} does not exist."
            )

        if (
            attrs["config_type"] == PluginConfig.ConfigType.PARAMETER
            and attrs["attribute"] not in config_obj.params
        ):
            raise ValidationError(
                f"{self.category} {attrs['plugin_name']} does not "
                f"have parameter {attrs['attribute']}."
            )
        elif (
            attrs["config_type"] == PluginConfig.ConfigType.SECRET
            and attrs["attribute"] not in config_obj.secrets
        ):

            raise ValidationError(
                f"{self.category} {attrs['plugin_name']} does not "
                f"have secret {attrs['attribute']}."
            )
        # Check if the type of value is valid for the attribute.

        expected_type = (
            config_obj.params[attrs["attribute"]].type
            if attrs["config_type"] == PluginConfig.ConfigType.PARAMETER
            else config_obj.secrets[attrs["attribute"]].type
        )
        if expected_type == "str":
            expected_type = str
        elif expected_type == "list":
            expected_type = list
        elif expected_type == "dict":
            expected_type = dict
        elif expected_type in ["int", "float"]:
            expected_type = int
        elif expected_type == "bool":
            expected_type = bool

        if expected_type and not isinstance(
            attrs["value"],
            expected_type,
        ):
            raise ValidationError(
                f"{self.category} {attrs['plugin_name']} attribute "
                f"{attrs['attribute']} has wrong type "
                f"{type(attrs['value']).__name__}. Expected: "
                f"{expected_type.__name__}."
            )

        inclusion_params = attrs.copy()
        exclusion_params = {}
        inclusion_params.pop("value")
        if "organization" not in inclusion_params:
            inclusion_params["organization__isnull"] = True
        if self.instance is not None:
            exclusion_params["id"] = self.instance.id
        if (
            PluginConfig.objects.filter(**inclusion_params)
            .exclude(**exclusion_params)
            .exists()
        ):
            raise ValidationError(
                f"{self.category} {attrs['plugin_name']} "
                f"{self} attribute {attrs['attribute']} already exists."
            )
        return attrs
