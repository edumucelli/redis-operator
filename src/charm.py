#!/usr/bin/env python3
# This file is part of the Redis k8s Charm for Juju.
# Copyright 2021 Canonical Ltd.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3, as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranties of
# MERCHANTABILITY, SATISFACTORY QUALITY, or FITNESS FOR A PARTICULAR
# PURPOSE.  See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import logging
from typing import Dict, List

import yaml
from charmhelpers.core import hookenv
from ops import model
from ops.charm import CharmBase, ConfigChangedEvent
from ops.main import main

logger = logging.getLogger(__name__)

DEBUG_COUNT = 3


class RedisCharm(CharmBase):

    def __init__(self, *args):
        super().__init__(*args)
        self.log_debug('Initializing charm')

        self.framework.observe(self.on.start, self._on_config_changed)
        self.framework.observe(self.on.leader_elected, self._on_config_changed)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.upgrade_charm, self._on_config_changed)
        # self.framework.observe(self.on["peer"].relation_joined, self._on_config_changed)
        # self.framework.observe(self.on["peer"].relation_departed, self._on_config_changed)

    def _on_config_changed(self, event: ConfigChangedEvent):
        self.log_debug("_on_config_changed event")

        if self.model.unit.is_leader():
            self._handle_leader_config_change()
        else:
            self._handle_non_leader_config_change()

    def _handle_leader_config_change(self):
        msg = "Configuring pod"
        self.log_debug(msg)
        self.model.unit.status = model.MaintenanceStatus(msg)

        spec = self._make_pod_spec()
        self.log_debug(f"Pod spec:\n{yaml.dump(spec)}\n")
        resources = self._make_pod_resources()
        self.log_debug(f"Pod resources:\n{yaml.dump(resources)}\n")
        # Only the leader can set_spec().
        self.model.pod.set_spec(spec, {"kubernetesResources": resources})

        msg = "Pod configured"
        self.log_debug(msg)
        self.model.unit.status = model.ActiveStatus(msg)

    def _handle_non_leader_config_change(self):
        self.log_debug("Spec changes ignored by non-leader")
        self.model.unit.status = model.ActiveStatus()

    def _make_pod_spec(self) -> Dict:
        """Set up and return our full pod spec."""
        config_fields = {
            "JUJU_NODE_NAME": "spec.nodeName",
            "JUJU_POD_NAME": "metadata.name",
            "JUJU_POD_NAMESPACE": "metadata.namespace",
            "JUJU_POD_IP": "status.podIP",
            # "JUJU_POD_SERVICE_ACCOUNT": "spec.serviceAccountName",
        }
        env_config = {k: {"field": {"path": p, "api-version": "v1"}} for k, p in config_fields.items()}

        env_config["JUJU_EXPECTED_UNITS"] = " ".join(self.expected_units)
        env_config["JUJU_APPLICATION"] = self.app.name

        # vol_config = [
        #     {"name": "charm-secrets", "mountPath": "/charm-secrets", "secret": {"name": "charm-secrets"}},
        #     {"name": "var-run-postgresql", "mountPath": "/var/run/postgresql", "emptyDir": {"medium": "Memory"}},
        # ]

        config = self.model.config

        spec = {
            "version": 3,
            "containers": [
                {
                    "name": self.app.name,
                    "imageDetails": {
                        "imagePath": config["image"],
                    },
                    "imagePullPolicy": "Always",  # TODO: Necessary? Should this be a Juju default?
                    "ports": [
                        {"name": "redis", "containerPort": 6379, "protocol": "TCP"},
                    ],
                    "envConfig": env_config,
                    # "volumeConfig": vol_config,
                    "kubernetes": {
                        "readinessProbe": {"tcpSocket": {"port": 6379}, "initialDelaySeconds": 3, "periodSeconds": 3}
                    },
                }
            ],
            # "serviceAccount": {  # Required because we're interacting with the k8s API in this charm.
            #     "automountServiceAccountToken": True,
            #     "roles": [
            #         {
            #             "global": True,
            #             "rules": [
            #                 {
            #                     "apiGroups": [""],
            #                     "resources": ["pods"],
            #                     "verbs": ["get", "list", "patch"],
            #                 },
            #             ],
            #         },
            #     ],
            # },
        }

        # # After logging, attach our secrets.
        # if config.get("image_username"):
        #     image_details["username"] = config["image_username"]
        # if config.get("image_password"):
        #     image_details["password"] = config["image_password"]

        return spec

    def _make_pod_resources(self) -> Dict:
        """Compile and return our pod resources (e.g. ingresses)."""
        services = [
            {
                "name": f"{self.app.name}-master",
                "spec": {
                    "type": "NodePort",  # NodePort to enable external connections
                    # We require a stable IP address selected by k8s,
                    # so must specify the empty string for clusterIP.
                    # The default is the string 'None', which will
                    # give you an unstable IP address (the Pod's
                    # internal IP I believe).
                    "clusterIP": "",
                    "ports": [{"name": "redis", "port": 6379, "protocol": "TCP"}],
                    "selector": {"app.kubernetes.io/name": self.app.name, "role": "master"},
                },
            },
            # {
            #     "name": self.client_relations.standbys_service_name,
            #     "spec": {
            #         "type": "NodePort",  # NodePort to enable external connections
            #         "clusterIP": "",  # A stable IP address selected by k8s.
            #         "ports": [{"name": "pgsql", "port": 5432, "protocol": "TCP"}],
            #         "selector": {"app.kubernetes.io/name": self.app.name, "role": "standby"},
            #     },
            # },
        ]

        resources = {
            # "secrets": [{"name": "charm-secrets", "type": "Opaque", "data": secrets_data}],
            # TODO: How to only make the master and standbys services
            # externally available only after 'juju expose'?
            "services": services,
        }

        # secrets_data = {}  # Fill dictionary with secrets after logging.
        # # Fill secrets dict with secrets.
        # secrets = {"pgsql-admin-password": self.get_admin_password()}
        # for k, v in secrets.items():
        #     secrets_data[k] = b64encode(v.encode("UTF-8")).decode("UTF-8")

        return resources

    @property
    def expected_units(self) -> List[str]:
        # Goal state looks like this:
        #
        # relations: {}
        # units:
        #   redis/0:
        #     since: '2020-08-31 11:05:32Z'
        #     status: active
        #   redis/1:
        #     since: '2020-08-31 11:05:54Z'
        #     status: maintenance
        return sorted(hookenv.goal_state().get("units", {}).keys(), key=lambda x: int(x.split("/")[-1]))

    @staticmethod
    def log_debug(message: str):
        logger.debug(f"[Redis {DEBUG_COUNT}] %s", message)


if __name__ == "__main__":
    main(RedisCharm)
