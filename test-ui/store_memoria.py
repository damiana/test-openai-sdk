"""Store efêmero com autorização por proprietário em todas as operações."""
from collections import defaultdict

from chatkit.store import NotFoundError, Store
from chatkit.types import Page


class StoreMemoria(Store):
    def __init__(self):
        self.threads = {}
        self.items = defaultdict(dict)
        self.attachments = {}
        self.proprietarios = {}

    def autorizar_thread(self, thread_id, context):
        if self.proprietarios.get(thread_id) != context["user_id"]:
            raise NotFoundError("Conversa não encontrada.")

    async def load_thread(self, thread_id, context):
        self.autorizar_thread(thread_id, context)
        return self.threads[thread_id]

    async def save_thread(self, thread, context):
        if thread.id in self.proprietarios:
            self.autorizar_thread(thread.id, context)
        self.proprietarios[thread.id] = context["user_id"]
        self.threads[thread.id] = thread

    async def delete_thread(self, thread_id, context):
        self.autorizar_thread(thread_id, context)
        self.threads.pop(thread_id)
        self.proprietarios.pop(thread_id)
        self.items.pop(thread_id, None)
        callback = context.get("on_delete_thread")
        if callback:
            callback(thread_id)

    @staticmethod
    def _pagina(values, limit, after, order):
        values = sorted(values, key=lambda item: (item.created_at.timestamp(), item.id), reverse=order == "desc")
        if after is not None:
            index = next((i for i, item in enumerate(values) if item.id == after), None)
            if index is None:
                raise NotFoundError("Cursor não encontrado.")
            values = values[index + 1:]
        return Page(data=values[:limit], has_more=len(values) > limit)

    async def load_threads(self, limit, after, order, context):
        threads = [thread for tid, thread in self.threads.items()
                   if self.proprietarios[tid] == context["user_id"]]
        return self._pagina(threads, limit, after, order)

    async def add_thread_item(self, thread_id, item, context):
        self.autorizar_thread(thread_id, context)
        self.items[thread_id][item.id] = item

    async def save_item(self, thread_id, item, context):
        await self.add_thread_item(thread_id, item, context)

    async def load_item(self, thread_id, item_id, context):
        self.autorizar_thread(thread_id, context)
        try:
            return self.items[thread_id][item_id]
        except KeyError:
            raise NotFoundError("Item não encontrado.") from None

    async def delete_thread_item(self, thread_id, item_id, context):
        self.autorizar_thread(thread_id, context)
        self.items[thread_id].pop(item_id, None)

    async def load_thread_items(self, thread_id, after, limit, order, context):
        self.autorizar_thread(thread_id, context)
        return self._pagina(list(self.items[thread_id].values()), limit, after, order)

    async def save_attachment(self, attachment, context):
        # IDs também pertencem a um usuário; anexos não estão habilitados na UI.
        existing = self.attachments.get(attachment.id)
        if existing and existing[0] != context["user_id"]:
            raise NotFoundError("Anexo não encontrado.")
        self.attachments[attachment.id] = (context["user_id"], attachment)

    async def load_attachment(self, attachment_id, context):
        entry = self.attachments.get(attachment_id)
        if entry is None or entry[0] != context["user_id"]:
            raise NotFoundError("Anexo não encontrado.")
        return entry[1]

    async def delete_attachment(self, attachment_id, context):
        await self.load_attachment(attachment_id, context)
        self.attachments.pop(attachment_id)

    def remover_usuario(self, user_id):
        for tid in [tid for tid, owner in self.proprietarios.items() if owner == user_id]:
            self.threads.pop(tid, None)
            self.items.pop(tid, None)
            self.proprietarios.pop(tid, None)
        for aid in [aid for aid, (owner, _) in self.attachments.items() if owner == user_id]:
            self.attachments.pop(aid)
