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
# along with this program. If not, see <http://www.gnu.org/licenses/>.

import logging

import yaml
from oci_image import OCIImageResource, OCIImageResourceError
from ops.charm import CharmBase
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus

from src.client import RedisClient
from src.pod_spec import PodSpecBuilder

logger = logging.getLogger(__name__)

# We expect the redis container to use the default port
DEFAULT_PORT = 6379


class RedisCharm(CharmBase):
    state = StoredState()

    def __init__(self, *args):
        super().__init__(*args)
        self.log_debug('Initializing charm')

        self.state.set_default(pod_spec=None)

        self.image = OCIImageResource(self, "redis-image")

        self.framework.observe(self.on.start, self.on_start)
        self.framework.observe(self.on.stop, self.on_stop)
        self.framework.observe(self.on.config_changed, self.configure_pod)
        self.framework.observe(self.on.upgrade_charm, self.configure_pod)
        self.framework.observe(self.on.update_status, self.update_status)

    def on_start(self, event):
        """Initialize Redis

        This event handler is deferred if initialization of Redis fails.
        """
        self.log_debug("Running on_start")
        if not self.unit.is_leader():
            self.unit.status = ActiveStatus('Pod is ready.')
            return

        if not self.redis.is_ready():
            msg = 'Waiting for Redis ...'
            self.unit.status = WaitingStatus(msg)
            self.log_debug(msg)
            event.defer()
            return

        self.pod_is_ready()
        self.log_debug("Running on_start finished")

    def on_stop(self, _):
        """Mark terminating unit as inactive
        """
        self.unit.status = MaintenanceStatus('Pod is terminating.')

    def configure_pod(self, _):
        """Applies the pod configuration
        """
        self.log_debug("Running configure_pod")

        if not self.unit.is_leader():
            self.log_debug("Spec changes ignored by non-leader")
            self.unit.status = ActiveStatus('Pod is ready.')
            return

        msg = 'Configuring pod.'
        self.log_debug(msg)
        self.unit.status = WaitingStatus(msg)

        # Fetch image information
        try:
            self.unit.status = WaitingStatus("Fetching image information ...")
            image_info = self.image.fetch()
        except OCIImageResourceError:
            self.unit.status = BlockedStatus(
                "Error fetching image information.")
            return

        # Build Pod spec
        builder = PodSpecBuilder(
            name=self.model.app.name,
            port=DEFAULT_PORT,
            image_info=image_info,
        )

        spec = builder.build_pod_spec()
        self.log_debug(f"Pod spec:\n{yaml.dump(spec)}\n")

        # Update pod spec if the generated one is different
        # from the one previously applied
        if self.state.pod_spec == spec:
            self.log_debug("Discarding pod spec because it has not changed.")
        else:
            self.log_debug("Applying new pod spec.")
            self.model.pod.set_spec(spec)
            self.state.pod_spec = spec

        self.pod_is_ready()
        self.log_debug("Running configure_pod finished")

    def update_status(self, _):
        """Set status for all units

        Status may be
        - Redis API server not reachable (service is not ready),
        - Ready
        """
        if not self.unit.is_leader():
            self.unit.status = ActiveStatus('Pod is ready.')
            return

        if not self.redis.is_ready():
            self.unit.status = WaitingStatus('Waiting for Redis ...')
            return

        self.pod_is_ready()

    def pod_is_ready(self):
        status_message = 'Pod is ready.'
        self.log_debug(status_message)
        self.unit.status = ActiveStatus(status_message)
        self.app.status = ActiveStatus('Redis is ready.')

    @staticmethod
    def log_debug(message: str):
        logger.debug("[Redis] {}".format(message))

    @property
    def redis(self):
        """Return a Redis API client
        """
        return RedisClient(host=self.model.app.name, port=DEFAULT_PORT)


if __name__ == "__main__":
    main(RedisCharm)
