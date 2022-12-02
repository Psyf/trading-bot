import datetime
from telethon import TelegramClient, events
from models import Message
import re
import os
from dotenv import load_dotenv

dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path)

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
    num_brags = {}
    for i in range(6):
        num_brags[i + 1] = 0
    num_calls = 0
    client.start()
    for message in client.iter_messages(
        entity="Over99PercentWins",
        offset_date=datetime.datetime(2022, 11, 20),
        reverse=True,
    ):
        if "Take-Profit Number" in message.text:
            match = re.search(r"Take-Profit Number (\d+)", message.text)
            if match:
                # The number is the first group in the regex match
                number = match.group(1)
                num_brags[int(number)] += 1
        elif "All take-profit targets achieved" in message.text:
            num_brags[6] += 1
        elif "Setup" in message.text:
            num_calls += 1
        else:
            print(message.text)
            # raise Exception("Unknown message type")

        # Check if message.id is already in the database
        new_message = Message(id=message.id, date=message.date, text=message.text)
        if not session.query(Message).where(Message.id == message.id).first():
            session.add(new_message)
            session.commit()
            print("New Message:\n", message.date, "\n", message.id, "\n", message.text)
        # else:
        # print(message.id, "already in database")

    print(num_calls)
    print(num_brags)
    for k, v in num_brags.items():
        print(k, "=> ", v / num_calls)


# print new messages as they arrive
@client.on(events.NewMessage(chats="Over99PercentWins"))
async def handler(event):
    print(event.message.text)


main()
client.run_until_disconnected()
