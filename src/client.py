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

logger = logging.getLogger(__name__)


class RedisClient:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port

    def is_ready(self) -> bool:
        try:
            redis.Redis(host=self.host, port=self.port)
            logger.debug("Redis service is ready.")
            return True
        except redis.exceptions.ConnectionError as exc:
            logger.warning("Unable to connect to Redis: {}".format(exc))
        return False
