# This file is a part of IntelOwl https://github.com/intelowlproject/IntelOwl
# See the file 'LICENSE' for copying permission.

import requests

from api_app.exceptions import AnalyzerRunException
from api_app.analyzers_manager import classes
from ..serializers.AnalyzerConfigSerializer import ObservableTypes


class URLHaus(classes.ObservableAnalyzer):
    base_url = "https://urlhaus-api.abuse.ch/v1/"

    def run(self):
        headers = {"Accept": "application/json"}
        if self.observable_classification == ObservableTypes.DOMAIN.value:
            uri = "host/"
            post_data = {"host": self.observable_name}
        elif self.observable_classification == ObservableTypes.URL.value:
            uri = "url/"
            post_data = {"url": self.observable_name}
        else:
            raise AnalyzerRunException(
                f"not supported observable type {self.observable_classification}."
                f" Supported are: domain and url."
            )

        try:
            response = requests.post(
                self.base_url + uri, data=post_data, headers=headers
            )
            response.raise_for_status()
        except requests.RequestException as e:
            raise AnalyzerRunException(e)

        return response.json()
