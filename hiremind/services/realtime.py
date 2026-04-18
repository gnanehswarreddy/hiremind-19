from models.notification_model import NotificationModel


def stream_notifications():
    return NotificationModel._collection().watch([], full_document="updateLookup")


def stream_messages():
    from models.message_model import MessageModel

    return MessageModel._collection().watch([], full_document="updateLookup")
