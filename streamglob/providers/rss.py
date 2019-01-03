from streamglob.providers.base import *

from ..exceptions import *
from ..state import *
from .. import config

from .filters import *

import feedparser
from datetime import datetime
from time import mktime

# class RSSFeedsFilter(ListingFilter):

#     @property
#     def values(self):
#         return state.provider_config.feeds


@with_view(SimpleProviderView)
class RSSProvider(FeedProvider):

    ATTRIBUTES = AttrDict(
        time = {"width": 19},
        title = {"width": ("weight", 1)},
    )

    MEDIA_TYPES = {"video"}

    def listings(self, offset=None, limit=None, *args, **kwargs):

        for item in feedparser.parse(self.selected_feed).entries:
            yield AttrDict(
                time =  datetime.fromtimestamp(
                    mktime(item.published_parsed)
                ),
                title = item.title,
                url = item.link
            )
