import asyncio
from math import ceil
from queue import Full
from time import monotonic

from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.constants import ChatType
from telegram.error import BadRequest, TelegramError
from telegram.ext import (
    ApplicationHandlerStop,
    CommandHandler,
    MessageHandler,
    TypeHandler,
    filters,
)

from agencykey import AgencyKey, AgencyKeyError
from config import log
from core import Batch, Post, SessionStats

NEW_BATCH = "🔄 Nuevo Drop"
PUBLISH = "📤 Publicar"
PUBLISH_NORMAL = "📤 Publicar normal"
PUBLISH_SLOW = "🐢 Publicar lento"
RESUME_SLOW = "🐢 Continuar lento"
CONTROL_TEXTS = {PUBLISH, PUBLISH_NORMAL, PUBLISH_SLOW}
CANCEL = "❌ Cancelar Drop"
CONTINUE = "▶️ Continuar"


def without_final_periods(text):
    return '\n'.join(line[:-1] if line.endswith('.') and not line.endswith('..') else line
                     for line in text.split('\n'))


class DropperBot:
    def __init__(self, agencykey: AgencyKey, creator=None, recording=None, events=None):
        self.agencykey = agencykey
        self.creator = creator
        self.session = SessionStats()
        self.recording = recording
        self.events = events
        if recording:
            recording.completion_markup = ReplyKeyboardMarkup([[NEW_BATCH]], resize_keyboard=True, is_persistent=True)

    def show_batch(self, batch, stage=""):
        if self.events is None:
            return
        try:
            self.events.put_nowait(("publication", {
                "id": batch.id, "status": batch.status, "stage": stage, "total": len(batch.order) or len(batch.received),
                "completed": batch.cursor, "manual": tuple(batch.manual), "mention": batch.rejected_mention,
                "failed": batch.failed, "uncertain": batch.uncertain, "rate_limited": batch.retry_at is not None,
            }))
        except Full:
            log.warning("No se pudo actualizar el panel de publicación")

    async def authorize(self, update, context):
        if (
            not update.effective_user
            or not update.effective_chat
            or update.effective_chat.type != ChatType.PRIVATE
        ):
            raise ApplicationHandlerStop
        batch = context.user_data.get("batch")
        message = update.effective_message
        if message and (not batch or batch.status in {"collecting", "done"}):
            if message.text not in CONTROL_TEXTS | {"/publicar"} or message.forward_origin or message.photo:
                context.user_data.setdefault("prepublish_ids", set()).add(message.message_id)
        pending_error = context.user_data.get("telegram_error")
        if pending_error and await self.notify(context, update.effective_chat.id, pending_error):
            context.user_data.pop("telegram_error", None)

    @staticmethod
    def keyboard(context):
        batch = context.user_data.get("batch")
        rows = []
        if batch and batch.status == "collecting":
            if batch.received:
                rows.append([PUBLISH_NORMAL, PUBLISH_SLOW])
            rows.append([CANCEL])
        elif batch and batch.status == "paused":
            rows.append([CONTINUE, RESUME_SLOW] if batch.retry_at is not None else [CONTINUE])
            rows.append([CANCEL])
        elif batch and batch.status == "publishing":
            return ReplyKeyboardRemove()
        else:
            rows = [[NEW_BATCH]]
        return ReplyKeyboardMarkup(rows, resize_keyboard=True, is_persistent=True)

    async def start(self, update, context):
        batch = context.user_data.get("batch")
        if batch and batch.status != "done":
            await self.status(update, context)
            return
        if self.creator is None:
            await self.reply(update, context, "⚙️ Asigna una modelo desde la app de escritorio")
            return
        context.user_data["batch"] = Batch(self.creator)
        self.show_batch(context.user_data["batch"])
        log.info("Drop abierto para %s", self.creator.name)
        await self.reply(update, context,
            f"🔄 {self.creator.name}\nReenvía tus mensajes",
            reply_markup=self.keyboard(context))

    async def menu(self, update, context):
        message = update.effective_message
        if message.forward_origin or message.photo or message.caption or message.media_group_id:
            await self.receive(update, context)
            return
        handlers = {NEW_BATCH: self.start, PUBLISH: self.publish, PUBLISH_NORMAL: self.publish,
                    PUBLISH_SLOW: self.publish, CANCEL: self.cancel,
                    CONTINUE: self.resume, RESUME_SLOW: self.resume}
        if message.text in handlers:
            await handlers[message.text](update, context)
        else:
            await self.receive(update, context)

    async def receive(self, update, context):
        batch = context.user_data.get("batch")
        if batch is None or batch.status == "done":
            await self.start(update, context)
            batch = context.user_data.get("batch")
            if batch is None or batch.status == "done":
                return
        if batch.status != "collecting":
            await self.status(update, context)
            return
        message = update.effective_message
        if message.media_group_id:
            batch.rejected.add(message.message_id)
            self.schedule_queue_notice(context, update.effective_chat.id, batch)
            log.warning("Álbum rechazado · Envía mensajes individuales")
            return
        if message.message_id in batch.received:
            return
        photo_id = message.photo[-1].file_id if message.photo else None
        text = message.text or message.caption or ""
        if not photo_id and not text.strip():
            return
        batch.received[message.message_id] = Post(text, photo_id)
        self.show_batch(batch)
        log.info("Drop %s | Post #%d en cola | Foto: %s.", batch.id, len(batch.received), bool(photo_id))
        context.user_data.setdefault("prepublish_ids", set()).add(message.message_id)
        self.schedule_queue_notice(context, update.effective_chat.id, batch)

    async def publish(self, update, context):
        if self.recording and self.recording.busy:
            await self.reply(update, context, '🎥 Espera a que termine el comprobante actual antes de publicar el siguiente Drop')
            return
        batch = context.user_data.get("batch")
        if batch is None or batch.status != "collecting":
            await self.status(update, context)
            return
        if not batch.received:
            await self.reply(update, context, "📥 Reenvía al menos un post antes de publicar",
                                                      reply_markup=self.keyboard(context))
            return
        self.cancel_queue_notice(context)
        batch.cleanup_ids.update(context.user_data.pop("prepublish_ids", set()))
        batch.order = sorted(batch.received, reverse=True)
        batch.slow = update.effective_message.text == PUBLISH_SLOW
        await self.publish_batch(batch, update, context)

    async def resume(self, update, context):
        if self.recording and self.recording.busy:
            await self.reply(update, context, '🎥 Espera a que termine el comprobante actual antes de continuar la publicación')
            return
        batch = context.user_data.get("batch")
        if batch is None or batch.status != "paused":
            await self.status(update, context)
            return
        if batch.retry_at is not None and monotonic() < batch.retry_at:
            await self.report(update, context)
            return
        if update.effective_message.text == RESUME_SLOW:
            batch.slow = True
        if batch.failed:
            if not batch.recovery_delivered:
                await self.report(update, context)
                return
            number = batch.cursor + 1
            batch.confirm_manual()
            self.session.manual += 1
            await self.notify(context, update.effective_chat.id,
                              f"✅ Post #{number} publicado manualmente · Continuando")
        await self.publish_batch(batch, update, context)

    async def publish_batch(self, batch, update, context):
        batch.start_timer()
        async def download_photo(file_id: str) -> bytes:
            try:
                file = await context.bot.get_file(file_id)
                return bytes(await file.download_as_bytearray(read_timeout=60))
            except (TelegramError, RuntimeError) as error:
                raise AgencyKeyError(f"Descarga de Telegram: {type(error).__name__}.") from error

        chat_id = update.effective_chat.id
        loading = None

        try:
            loading = await context.bot.send_message(
                chat_id, f"📤 Publicando · {batch.creator.name}",
                reply_markup=ReplyKeyboardRemove(),
            )
        except TelegramError:
            log.exception("No se pudo mostrar el progreso")

        async def progress(text):
            if text.startswith("✅"):
                await self.notify(context, chat_id, text)
            elif loading:
                try:
                    await context.bot.edit_message_text(
                        without_final_periods(text), chat_id=chat_id, message_id=loading.message_id,
                    )
                except TelegramError:
                    log.debug("No se pudo actualizar el progreso", exc_info=True)

        try:
            await batch.publish(self.agencykey, download_photo, progress, session=self.session,
                                on_stage=lambda stage: self.show_batch(batch, stage))
            self.show_batch(batch)
        finally:
            if loading:
                try:
                    await context.bot.delete_message(chat_id, loading.message_id)
                except TelegramError:
                    log.debug("No se pudo retirar el progreso", exc_info=True)
        if batch.status == 'done' and self.recording:
            batch.session_total = self.session.total
            await self.cleanup(context, chat_id, batch)
            await self.recording.start(batch, context.bot, chat_id, context.application)
        else:
            await self.report(update, context)

    async def video(self, update, context):
        batch = context.user_data.get('batch')
        if self.recording and (not batch or batch.status != 'done'):
            batch = self.recording.restore_batch(update.effective_chat.id)
        if not self.recording or not batch or batch.status != 'done':
            await self.reply(update, context, 'Finaliza primero el Drop para generar su comprobante')
            return
        await self.recording.start(batch, context.bot, update.effective_chat.id, context.application,
                                   resend=getattr(context, 'args', []) == ['reenviar'])

    async def manual_id(self, update, context):
        from recorder import post_id
        batch = context.user_data.get('batch')
        try:
            number, value = context.args
            number = int(number)
            value = post_id(value)
            if not batch or batch.status != 'done' or number not in batch.manual:
                raise ValueError()
            if value in batch.published_ids.values():
                raise ValueError()
        except (ValueError, TypeError):
            await self.reply(update, context, 'Usa /id NUMERO ID_O_ENLACE para un post confirmado manualmente del último Drop')
            return
        batch.published_ids[number] = value
        await self.reply(update, context, f'ID del post #{number} guardado · Usa /video cuando hayas indicado todos')

    @staticmethod
    def cancel_queue_notice(context):
        task = context.user_data.pop("queue_notice_task", None)
        if task:
            task.cancel()

    def schedule_queue_notice(self, context, chat_id, batch):
        task = context.user_data.get("queue_notice_task")
        if task and not task.done():
            return
        context.user_data["queue_notice_task"] = asyncio.create_task(self.queue_notice(context, chat_id, batch))

    def queue_text(self, batch):
        text = f"✅ {len(batch.received)} posts en cola"
        if batch.rejected:
            text += (f"\n⚠️ {len(batch.rejected)} mensajes rechazados"
                     "\nEnvía cada foto con su texto como mensaje individual")
        return text

    async def queue_notice(self, context, chat_id, batch):
        try:
            while True:
                await asyncio.sleep(1.2)
                if context.user_data.get("batch") is not batch or batch.status != "collecting":
                    return
                version = (len(batch.received), len(batch.rejected))
                await self.update_queue_notice(context, chat_id, self.queue_text(batch), bool(version[0]))
                if version == (len(batch.received), len(batch.rejected)):
                    return
        except TelegramError:
            log.exception("No se pudo confirmar la cola")

    async def update_queue_notice(self, context, chat_id, text, has_posts):
        message_id = context.user_data.get("queue_notice_id")
        # Telegram requires a new message to replace the reply keyboard.
        if has_posts and not context.user_data.get("queue_keyboard_has_posts"):
            message_id = None
        if message_id:
            try:
                await context.bot.edit_message_text(without_final_periods(text), chat_id=chat_id, message_id=message_id)
                return
            except BadRequest as error:
                if "message is not modified" in str(error).lower():
                    return
                log.debug("Se recreará el aviso de cola", exc_info=True)
        message = await context.bot.send_message(chat_id, text, reply_markup=self.keyboard(context))
        context.user_data["queue_notice_id"] = message.message_id
        context.user_data["queue_keyboard_has_posts"] = has_posts
        context.user_data.setdefault("prepublish_ids", set()).add(message.message_id)

    @staticmethod
    async def reply(update, context, text, **kwargs):
        message = await update.effective_message.reply_text(without_final_periods(text), **kwargs)
        batch = context.user_data.get("batch")
        if not batch or batch.status in {"collecting", "done"}:
            context.user_data.setdefault("prepublish_ids", set()).add(message.message_id)
        return message

    async def cleanup(self, context, chat_id, batch):
        failed = 0
        for message_id in sorted(batch.cleanup_ids):
            try:
                await context.bot.delete_message(chat_id, message_id)
            except TelegramError:
                failed += 1
                log.warning("No se pudo borrar el mensaje %s", message_id, exc_info=True)
        batch.cleanup_ids.clear()
        context.user_data.pop("queue_notice_id", None)
        context.user_data.pop("queue_keyboard_has_posts", None)
        if failed:
            await self.notify(context, chat_id, f"🧹 No se pudieron borrar {failed} mensajes")

    @staticmethod
    async def notify(context, chat_id, text, reply_markup=None):
        log.info("Telegram | Chat %s | %s", chat_id, text)
        try:
            await context.bot.send_message(chat_id, without_final_periods(text), reply_markup=reply_markup)
            return True
        except TelegramError:
            log.exception("Telegram | Chat %s | No se pudo entregar el aviso.", chat_id)
            return False

    async def report(self, update, context):
        batch = context.user_data["batch"]
        confirmed = batch.confirmed
        if batch.status == "done":
            await self.cleanup(context, update.effective_chat.id, batch)
            if self.recording:
                await self.notify(context, update.effective_chat.id,
                                  '🎥 Comprobante en proceso' if self.recording.busy else '🎥 Usa /video para consultar el comprobante',
                                  reply_markup=self.keyboard(context))
                return
            text = (f"✅ Drop finalizado · {batch.creator.name}\n"
                    f"📦 Total del Drop: {batch.cursor}\n"
                    f"⏱ Tiempo total: {batch.elapsed_text}\n\n"
                    f"🔄 Bot · {batch.creator.name}\n"
                    f"🗂 Total de post: {self.session.total} posts\n")
            if batch.rejected:
                text += f"\n⚠️ Mensajes rechazados: {len(batch.rejected)}"
        elif batch.status == "publishing":
            text = f"📤 {batch.creator.name} · {confirmed}/{len(batch.order)} confirmadas"
        else:
            text = (f"⏸ Drop pausado · {batch.creator.name}\n"
                    f"Post #{batch.cursor + 1} de {len(batch.order)}\n")
            if batch.retry_at is not None:
                remaining = max(0, ceil(batch.retry_at - monotonic()))
                text += "El servicio limitó temporalmente las publicaciones.\n"
                if remaining:
                    text += f"Espera {remaining} s antes de continuar."
                else:
                    text += "Puedes continuar desde la publicación pendiente."
            elif batch.failed:
                await self.send_recovery(context, update.effective_chat.id, batch)
                if batch.rejected_mention:
                    text += f"AgencyKey rechazó la mención {batch.rejected_mention} · HTTP 400\n"
                if batch.uncertain:
                    text += "🔎 Revisa si aparece en el feed antes de subirlo manualmente\n"
                text += "Sube este post manualmente y pulsa ▶️ Continuar\n"
                if not batch.recovery_delivered:
                    text += "\n⚠️ No se pudo entregar la copia; pulsa /estado para volver a solicitarla"
            else:
                text += "▶️ Continuar retoma desde este post pendiente"
        delivered = await self.notify(context, update.effective_chat.id, text, reply_markup=self.keyboard(context))
        if delivered and batch.status == "done":
            self.show_batch(batch, "Confirmación enviada a Telegram")

    async def send_recovery(self, context, chat_id, batch):
        if batch.recovery_delivered:
            return
        message_id = batch.order[batch.cursor]
        try:
            await context.bot.copy_message(chat_id=chat_id, from_chat_id=chat_id, message_id=message_id)
            batch.recovery_delivered = True
            return
        except TelegramError:
            log.info("No se pudo copiar el original; se reconstruirá el post")
        post = batch.received[message_id]
        short_caption = len(post.text.encode("utf-16-le")) // 2 <= 1024
        try:
            if post.photo_id:
                await context.bot.send_photo(chat_id=chat_id, photo=post.photo_id,
                                             caption=post.text if short_caption else None)
            if not post.photo_id or not short_caption:
                # 2,000 code points also fit Telegram's 4,096 UTF-16 unit limit.
                for offset in range(0, len(post.text), 2000):
                    await context.bot.send_message(chat_id, post.text[offset:offset + 2000])
            batch.recovery_delivered = True
        except TelegramError:
            log.exception("No se pudo entregar la publicación para carga manual")

    async def status(self, update, context):
        batch = context.user_data.get("batch")
        if batch is None:
            await self.start(update, context)
        elif batch.status == "collecting":
            await self.reply(update, context,
                self.queue_text(batch), reply_markup=self.keyboard(context)
            )
        else:
            await self.report(update, context)

    async def cancel(self, update, context):
        batch = context.user_data.get("batch")
        if batch is None or batch.status == "done":
            await self.reply(update, context, "📭 Sin Drop activo", reply_markup=self.keyboard(context))
            return
        self.cancel_queue_notice(context)
        context.user_data.pop("queue_notice_id", None)
        context.user_data.pop("queue_keyboard_has_posts", None)
        del context.user_data["batch"]
        batch.status = "cancelled"
        self.show_batch(batch)
        confirmed = batch.confirmed
        log.info("Drop %s cancelado con %d publicaciones confirmadas.", batch.id, confirmed)
        text = "🗑️ Drop cancelado"
        if batch.uncertain:
            text += "\n🔎 Revisa la publicación pendiente en el feed"
        await self.notify(context, update.effective_chat.id, text, reply_markup=self.keyboard(context))


async def on_error(update, context):
    stage = "procesamiento de un mensaje" if update is not None else "conexión o polling"
    log.error("Telegram | %s | %s", stage, type(context.error).__name__, exc_info=context.error)
    if update is not None and update.effective_chat:
        targets = [(update.effective_chat.id, context.user_data)]
    else:
        targets = [(chat_id, data) for chat_id, data in context.application.user_data.items()
                   if data.get("batch") and data["batch"].status != "done"]
    for chat_id, data in targets:
        text = "⚠️ Error de conexión con Telegram\nRevisa el registro de la app"

        if data is not None:
            data["telegram_error"] = text
        if await DropperBot.notify(context, chat_id, text) and data is not None:
            data.pop("telegram_error", None)


def register(app, agencykey, creator, recording=None, events=None):
    bot = DropperBot(agencykey, creator, recording, events)
    app.add_handler(TypeHandler(Update, bot.authorize), group=-1)
    app.add_handler(CommandHandler("start", bot.start))
    app.add_handler(CommandHandler("publicar", bot.publish))
    app.add_handler(CommandHandler("estado", bot.status))
    app.add_handler(CommandHandler("cancelar", bot.cancel))
    app.add_handler(CommandHandler("continuar", bot.resume))
    app.add_handler(CommandHandler('video', bot.video))
    app.add_handler(CommandHandler('id', bot.manual_id))
    app.add_handler(MessageHandler((filters.TEXT | filters.PHOTO) & ~filters.COMMAND, bot.menu))
    app.add_error_handler(on_error)





