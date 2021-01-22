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

import yaml
from client import RedisClient
from oci_image import OCIImageResource, OCIImageResourceError
from ops.charm import CharmBase
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus
from pod_spec import PodSpecBuilder

logger = logging.getLogger(__name__)

UNIT_ACTIVE_MSG = 'Pod is ready.'
UNIT_ACTIVE_STATUS = ActiveStatus(UNIT_ACTIVE_MSG)

# We expect the redis container to use the default port
DEFAULT_PORT = 6379


class RedisCharm(CharmBase):
    state = StoredState()

    def __init__(self, *args):
        super().__init__(*args)
        self.log_debug('Initializing charm')

        self.state.set_default(redis_initialized=False)
        self.image = OCIImageResource(self, "redis-image")

        self.framework.observe(self.on.start, self.on_start)
        self.framework.observe(self.on.stop, self.on_stop)
        self.framework.observe(self.on.config_changed, self.configure_pod)
        self.framework.observe(self.on.upgrade_charm, self.configure_pod)
        self.framework.observe(self.on.update_status, self.update_status)

    def configure_pod(self, event):
        """Applies the pod configuration
        """
        self.log_debug("Running configure_pod")

        if not self.unit.is_leader():
            self.log_debug("Spec changes ignored by non-leader")
            self.update_status(event)
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
                "Error fetching image information        # self._authed = True.")
            return

        # Build Pod spec
        builder = PodSpecBuilder(
            name=self.model.app.name,
            port=DEFAULT_PORT,
            image_info=image_info,
        )

        spec = builder.build_pod_spec()
        self.log_debug(f"Pod spec:\n{yaml.dump(spec)}\n")

        resources = builder.build_pod_resources()
        self.log_debug(f"Pod resources:\n{yaml.dump(resources)}\n")
        # Only the leader can set_spec().
        self.model.pod.set_spec(spec, resources)

        self.update_status(event)
        self.log_debug("Running configure_pod finished")

    def update_status(self, event):
        """Set status for all units

        Status may be
        - Redis API server not reachable (service is not ready),
        - Unit is active
        """
        if not self.unit.is_leader():
            self.unit.status = ActiveStatus()
            return

        if not self.redis.is_ready():
            self.unit.status = WaitingStatus('Redis not ready yet.')
            return

        if not self.state.redis_initialized:
            status_message = "Redis not initialized."
            self.unit.status = WaitingStatus(status_message)
            return

        self.log_debug(UNIT_ACTIVE_MSG)
        self.unit.status = UNIT_ACTIVE_STATUS
        self.app.status = ActiveStatus('Redis pod ready.')

    def on_start(self, event):
        """Initialize Redis

        This event handler is deferred if initialization of Redis fails.
        """
        self.log_debug("Running on_start")
        if not self.unit.is_leader():
            return

        if not self.redis.is_ready():
            msg = "Waiting for Redis Service."
            self.unit.status = WaitingStatus(msg)
            self.log_debug(msg)
            event.defer()

        if not self.state.redis_initialized:
            msg = "Initializing Redis."
            self.log_debug(msg)
            self.unit.status = WaitingStatus(msg)
            try:
                self.state.redis_initialized = True
                self.log_debug("Redis Initialized")
            except Exception as e:
                logger.info("Deferring on_start since : error={}".format(e))
                event.defer()

        self.update_status(event)
        self.log_debug("Running on_start finished")

    def on_stop(self, _):
        """Mark terminating unit as inactive
        """
        self.unit.status = MaintenanceStatus('Pod is terminating.')

    @staticmethod
    def log_debug(message: str):
        logger.debug(f"[Redis] %s", message)

    @property
    def redis(self):
        """Return a Redis API client
        """
        return RedisClient(host=self.model.app.name, port=DEFAULT_PORT)


if __name__ == "__main__":
    main(RedisCharm)
