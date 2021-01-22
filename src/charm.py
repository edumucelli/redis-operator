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

import redis
import yaml
from ops.charm import CharmBase, ConfigChangedEvent
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus

from pod_spec import PodSpecBuilder

logger = logging.getLogger(__name__)

REQUIRED_SETTINGS = ['image']

UNIT_ACTIVE_MSG = 'Pod is ready.'
UNIT_ACTIVE_STATUS = ActiveStatus(UNIT_ACTIVE_MSG)

# We expect the redis container to use the default port
DEFAULT_PORT = 6379


class RedisCharm(CharmBase):
    state = StoredState()

    def __init__(self, *args):
        super().__init__(*args)
        self.log_debug('Initializing charm')

        # self.state.set_default(redis_initialized=False)

        self.framework.observe(self.on.start, self.configure_pod)
        self.framework.observe(self.on.stop, self.on_stop)
        self.framework.observe(self.on.config_changed, self.configure_pod)
        self.framework.observe(self.on.upgrade_charm, self.configure_pod)
        self.framework.observe(self.on.update_status, self.on_update_status)

    def configure_pod(self, event: ConfigChangedEvent):
        """Applies the pod configuration
        """
        logger.debug("Running configure_pod")

        if not self._is_config_valid():
            msg = 'Charm config is not valid'
            logger.warning(msg)
            self.model.unit.status = BlockedStatus(msg)
            return

        if not self.model.unit.is_leader():
            self.log_debug("Spec changes ignored by non-leader")
            self.model.unit.status = UNIT_ACTIVE_STATUS
            return

        msg = 'Configuring pod.'
        self.log_debug(msg)
        self.model.unit.status = WaitingStatus(msg)

        builder = PodSpecBuilder(
            name=self.model.app.name,
            port=DEFAULT_PORT,
            image_info=self.model.config['image'],
        )

        spec = builder.build_pod_spec()
        self.log_debug(f"Pod spec:\n{yaml.dump(spec)}\n")

        resources = builder.build_pod_resources()
        self.log_debug(f"Pod resources:\n{yaml.dump(resources)}\n")
        # Only the leader can set_spec().
        self.model.pod.set_spec(spec, resources)

        self.log_debug(UNIT_ACTIVE_MSG)
        self.model.unit.status = UNIT_ACTIVE_STATUS
        self.app.status = ActiveStatus('Redis pod ready.')

        logger.debug("Running configure_pod finished")

    def _is_config_valid(self) -> bool:
        """Validates the charm config
        :returns: boolean representing whether the config is valid or not.
        """
        logger.info('Validating charm config')

        config = self.model.config
        missing = []
        for name in REQUIRED_SETTINGS:
            if not config.get(name):
                missing.append(name)

        if missing:
            msg = 'Missing configuration: {}'.format(missing)
            logger.warning(msg)
            self.model.unit.status = BlockedStatus(msg)
            return False

        logger.info('Charm config validated')
        return True

    # Handles update-status event
    def on_update_status(self, event):
        """Set status for all units

        Status may be
        - [TODO] Redis API server not reachable (service is not ready),
        - Unit is active
        """
        if not self.model.unit.is_leader():
            self.model.unit.status = ActiveStatus()
            return

        # if not self.redis.is_ready():
        #     self.unit.status = WaitingStatus('Redis not ready yet')
        #     return

        self.unit.status = ActiveStatus()

    def on_stop(self, _):
        """Mark terminating unit as inactive
        """
        self.model.unit.status = MaintenanceStatus('Pod is terminating.')

    @staticmethod
    def log_debug(message: str):
        logger.debug(f"[Redis] %s", message)

    @property
    def redis(self):
        """Return a Redis API client
        """
        return redis.from_url(self.redis_uri)

    @property
    def redis_uri(self):
        """Construct a Redis URI
        """
        return "redis://{}:{}/".format(
            self.model.app.name,
            DEFAULT_PORT
        )


if __name__ == "__main__":
    main(RedisCharm)
