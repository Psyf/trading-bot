import datetime
from telethon import TelegramClient, events
from models import TradingCall
import os
from dotenv import load_dotenv
from parse_call import TradingCallParser
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path)

client = TelegramClient(
    "name", int(os.getenv("TELEGRAM_API_ID")), os.getenv("TELEGRAM_API_HASH")
)

# Create an engine that connects to the database
engine = create_engine("sqlite:///tradingbot.db")
session = sessionmaker(bind=engine)()
TradingCall.metadata.create_all(engine, checkfirst=True)


def main():
    client.start()
    offset_date = (
        datetime.datetime.now() - datetime.timedelta(days=5)
    ).date()  # Get from 2 days ago
    for message in client.iter_messages(
        entity="Over99PercentWins",
        offset_date=offset_date,
        reverse=True,
    ):
        filter_and_save(message)


# print new messages as they arrive
@client.on(events.NewMessage(chats="Over99PercentWins"))
async def handler(event):
    filter_and_save(event.message)


def filter_and_save(message):
    if "setup" in message.text.lower():
        if not session.query(TradingCall).get(message.id):
            try:
                new_call = TradingCallParser().parse(message)
                session.add(new_call)
                session.commit()
                print("New call => ", new_call)
            except:
                print("Could not parse call => ", message.id)
        else:
            print("Already exists => ", message.id)


main()
client.run_until_disconnected()
