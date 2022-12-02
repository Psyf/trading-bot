import datetime
from telethon import TelegramClient, events
from models import TradingCall
import re
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
    num_brags = {}
    for i in range(6):
        num_brags[i + 1] = 0
    num_calls = 0
    client.start()
    for message in client.iter_messages(
        entity="Over99PercentWins",
        offset_date=datetime.datetime(2022, 12, 2),
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
        elif "setup" in message.text.lower():
            num_calls += 1
        else:
            print("UNKNOWN MESSAGE ->", message.text)

        filter_and_save(message)

    print(num_calls)
    print(num_brags)
    for k, v in num_brags.items():
        print(k, "=> ", v / num_calls)


# print new messages as they arrive
@client.on(events.NewMessage(chats="Over99PercentWins"))
async def handler(event):
    filter_and_save(event.message)


def filter_and_save(message):
    if "setup" in message.text.lower():
        if not session.query(TradingCall).get(message.id):
            new_call = TradingCallParser().parse(message)
            session.add(new_call)
            session.commit()
            print(new_call)
        else:
            print("Already exists")


main()
client.run_until_disconnected()
