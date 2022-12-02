import datetime
from telethon import TelegramClient, events
from models import Message
import re
import os

client = TelegramClient(
    "name", int(os.getenv("TELEGRAM_API_ID")), os.getenv("TELEGRAM_API_HASH")
)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Create an engine that connects to the database
engine = create_engine("sqlite:///tradingbot.db")
session = sessionmaker(bind=engine)()
Message.metadata.create_all(engine, checkfirst=True)


def main():
    client.start()
    for message in client.iter_messages(
        entity="Over99PercentWins",
        offset_date=datetime.datetime(2022, 12, 1),
        reverse=True,
    ):
        new_message = Message(id=message.id, date=message.date, text=message.text)
        if not session.query(Message).where(Message.id == message.id).first():
            session.add(new_message)
            session.commit()
            print("New Message:\n", message.date, "\n", message.id, "\n", message.text)
        else:
            print(message.id, "already in database")


@client.on(events.NewMessage(chats="Over99PercentWins"))
async def handler(event):
    print(event.message.text)


main()
client.run_until_disconnected()
