# This file is a part of IntelOwl https://github.com/intelowlproject/IntelOwl
# See the file 'LICENSE' for copying permission.

import datetime

import pymisp
from django.conf import settings

from api_app.analyzers_manager import classes
from api_app.analyzers_manager.exceptions import (
    AnalyzerConfigurationException,
    AnalyzerRunException,
)
from tests.mock_utils import MockResponseNoOp, if_mock_connections, patch


class MISP(classes.ObservableAnalyzer):
    def set_params(self, params):
        self.ssl_check = params.get("ssl_check", True)
        self.self_signed_certificate = params.get("self_signed_certificate", False)
        self.debug = params.get("debug", False)
        self.from_days = params.get("from_days", 90)
        self.limit = params.get("limit", 50)
        self.enforce_warninglist = params.get("enforce_warninglist", True)
        self.filter_on_type = params.get("filter_on_type", True)
        self.__url_name = self._secrets["url_key_name"]
        self.__api_key = self._secrets["api_key_name"]
        self.strict_search = params.get("strict_search", True)

    def run(self):
        # this allows self-signed certificates to be used
        ssl_param = (
            f"{settings.PROJECT_LOCATION}/configuration/misp_ssl.crt"
            if self.ssl_check and self.self_signed_certificate
            else self.ssl_check
        )
        misp_instance = pymisp.PyMISP(
            url=self.__url_name,
            key=self.__api_key,
            ssl=ssl_param,
            debug=self.debug,
            timeout=5,
        )
        now = datetime.datetime.now()
        date_from = now - datetime.timedelta(days=self.from_days)
        params = {
            "limit": self.limit,
            "enforce_warninglist": self.enforce_warninglist,
        }
        if self.strict_search:
            params["value"] = self.observable_name
        else:
            string_wildcard = f"%{self.observable_name}%"
            params["searchall"] = string_wildcard
        if self.from_days != 0:
            params["date_from"] = date_from.strftime("%Y-%m-%d %H:%M:%S")
        if self.filter_on_type:
            params["type_attribute"] = [self.observable_classification]
            if self.observable_classification == self.ObservableTypes.HASH:
                params["type_attribute"] = ["md5", "sha1", "sha256"]
            if self.observable_classification == self.ObservableTypes.IP:
                params["type_attribute"] = [
                    "ip-dst",
                    "ip-src",
                    "ip-src|port",
                    "ip-dst|port",
                    "domain|ip",
                ]
            elif self.observable_classification == self.ObservableTypes.DOMAIN:
                params["type_attribute"] = [self.observable_classification, "domain|ip"]
            elif self.observable_classification == self.ObservableTypes.HASH:
                params["type_attribute"] = ["md5", "sha1", "sha256"]
            elif self.observable_classification == self.ObservableTypes.URL:
                params["type_attribute"] = [self.observable_classification]
            elif self.observable_classification == self.ObservableTypes.GENERIC:
                pass
            else:
                raise AnalyzerConfigurationException(
                    f"Observable {self.observable_classification} not supported."
                    "Currently supported are: ip, domain, hash, url, generic."
                )
        result_search = misp_instance.search(**params)
        if isinstance(result_search, dict):
            errors = result_search.get("errors", [])
            if errors:
                raise AnalyzerRunException(errors)

        return {"result_search": result_search, "instance_url": self.__url_name}

    @classmethod
    def _monkeypatch(cls):
        patches = [
            if_mock_connections(
                patch("pymisp.PyMISP", return_value=MockResponseNoOp({}, 200)),
            )
        ]
        return super()._monkeypatch(patches=patches)
