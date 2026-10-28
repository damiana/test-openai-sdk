
from collections import defaultdict
from chatkit.store import Store

from chatkit.types import Page

class StoreMemoria(Store):
    def __init__(self):
        self.threads = {}
        self.items = defaultdict(dict)
        self.attachments = {}

    async def load_thread(self, thread_id, context):
        return self.threads.get(thread_id)

    async def save_thread(self, thread, context):
        self.threads[thread.id] = thread

    async def delete_thread(self, thread_id, context):
        self.threads.pop(thread_id, None)
        self.items.pop(thread_id, None)

    # async def load_threads(self, limit, after, order, context):
    #     threads = list(self.threads.values())
    #     return threads[:limit]

    async def load_threads(self, limit, after, order, context):
        threads = list(self.threads.values())

        return Page(
            data=threads[:limit],
            has_more=len(threads) > limit
    )


    async def add_thread_item(self, thread_id, item, context):
        self.items[thread_id][item.id] = item

    async def save_item(self, thread_id, item, context):
        self.items[thread_id][item.id] = item

    async def load_item(self, thread_id, item_id, context):
        return self.items[thread_id].get(item_id)

    async def delete_thread_item(self, thread_id, item_id, context):
        self.items[thread_id].pop(item_id, None)

    # async def load_thread_items(self, thread_id, limit, after, order, context):
    #     items = list(self.items[thread_id].values())
    #     return items[:limit]

    async def load_thread_items(self, thread_id, after, limit, order, context):
        items = list(self.items[thread_id].values())

        if order == "desc":
            items.reverse()

        if after is not None:
            indice = next(
                (i for i, item in enumerate(items) if item.id == after),
                None
            )
            if indice is not None:
                items = items[indice + 1:]

        return Page(
            data=items[:limit],
            has_more=len(items) > limit
        )


    async def save_attachment(self, attachment, context):
        self.attachments[attachment.id] = attachment

    async def load_attachment(self, attachment_id, context):
        return self.attachments.get(attachment_id)

    async def delete_attachment(self, attachment_id, context):
        self.attachments.pop(attachment_id, None)
