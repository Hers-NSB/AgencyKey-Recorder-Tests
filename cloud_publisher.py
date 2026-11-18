"""Publish to the server-bound model without a local AgencyKey key."""
import asyncio
from time import monotonic
from uuid import uuid4

from agencykey import (
    AgencyKeyError, PUBLISH_INTERVAL_SECONDS, SLOW_PUBLISH_INTERVAL_SECONDS,
    PublishRateLimited, UnconfirmedPost,
)
from cloud_client import CloudError


class CloudPublisher:
    def __init__(self, client, profile_id, revision, creator_id, stop_requested):
        self.client = client
        self.profile_id = profile_id
        self.revision = revision
        self.creator_id = creator_id
        self.stop_requested = stop_requested
        self.next_publish = 0

    async def publish_text(self, creator_id, text, *, expire=False, slow=False):
        return await self._publish(creator_id, text, slow=slow)

    async def publish_photo(self, creator_id, text, photo, *, slow=False):
        return await self._publish(creator_id, text, photo, slow=slow)

    async def _publish(self, creator_id, text, photo=None, *, slow):
        if creator_id != self.creator_id:
            raise AgencyKeyError('La modelo cambió. Actualiza la app antes de publicar.')
        while not self.stop_requested() and (remaining := self.next_publish - monotonic()) > 0:
            await asyncio.sleep(min(remaining, .25))
        if self.stop_requested():
            raise AgencyKeyError('Parada solicitada desde la ventana. No se envió este post.')
        try:
            result = await asyncio.to_thread(
                self.client.publish_post, self.profile_id, self.revision, str(uuid4()), text, photo, slow=slow,
            )
        except CloudError as error:
            if error.status == 429:
                raise PublishRateLimited(error.retry_after or '') from error
            if error.uncertain or (error.uncertain is None and error.retryable):
                raise UnconfirmedPost(str(error)) from error
            raise AgencyKeyError(str(error)) from error
        finally:
            interval = SLOW_PUBLISH_INTERVAL_SECONDS if slow else PUBLISH_INTERVAL_SECONDS
            self.next_publish = monotonic() + interval
        post_id = result.get('post_id') if isinstance(result, dict) else None
        if not isinstance(post_id, str) or not post_id.isascii() or not post_id.isdecimal() or int(post_id) <= 0:
            raise UnconfirmedPost('El servidor no devolvió un ID válido. Revisa el muro.')
        return int(post_id)
