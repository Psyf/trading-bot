from collections import defaultdict
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
    # num_brags = dict()
    # calls = defaultdict(dict)
    # for i in range(7):
    #     num_brags[i + 1] = 0
    # num_calls = 0
    client.start()
    offset_date = (
        datetime.datetime.now() - datetime.timedelta(days=5)
    ).date()  # Get from 2 days ago
    for message in client.iter_messages(
        entity="Over99PercentWins",
        offset_date=offset_date,
        reverse=True,
    ):

        # if "Setup" in message.text:
        #     try:
        #         call = TradingCallParser().parse(message)
        #         calls[message.id]["message"] = call
        #         calls[message.id]["loss"] = (
        #             call.stop_loss - call.entry[0]
        #         ) / call.entry[0]
        #         calls[message.id]["take_profit"] = [0] * 6
        #         continue
        #     except:
        #         print("Could not parse call => ", message.id, message.text)
        #         continue

        # try:
        #     orig_id = message.reply_to.reply_to_msg_id
        # except:
        #     # print("Does not have reply_to but is not setup? => ", message.id)
        #     continue

        # orig_call = None

        # try:
        #     orig_call = calls[orig_id]["message"]
        # except KeyError:
        #     # message was older than offset_date. Get it!
        #     for message_old in client.iter_messages("Over99PercentWins", ids=orig_id):
        #         orig_call = TradingCallParser().parse(message_old)
        #         calls[orig_id]["message"] = orig_call
        #         calls[orig_id]["loss"] = (
        #             orig_call.stop_loss - orig_call.entry[0]
        #         ) / orig_call.entry[0]
        #         calls[orig_id]["take_profit"] = [0] * 6

        # entry = orig_call.entry[0]

        # if "Take-Profit Number" in message.text:
        #     match = re.search(r"Take-Profit Number (\d+)", message.text)
        #     if match:
        #         # The number is the first group in the regex match
        #         number = match.group(1)
        #         calls[orig_id]["loss"] = 0
        #         target = orig_call.targets[int(number) - 1]
        #         calls[orig_id]["take_profit"][int(number) - 1] = (
        #             target - entry
        #         ) / entry
        #         num_brags[int(number)] += 1
        # elif "All take-profit targets achieved" in message.text:
        #     calls[orig_id]["loss"] = 0
        #     target = orig_call.targets[5]
        #     calls[orig_id]["take_profit"][5] = (target - entry) / entry
        #     num_brags[6] += 1
        # elif "Cancelled" in message.text:
        #     calls[orig_id]["loss"] = 0
        #     num_brags[7] += 1
        # else:
        #     print("UNKNOWN MESSAGE -> ", message.text)

        filter_and_save(message)

    # num_calls = len(calls.values())
    # print(len(calls.values()))
    # print(num_brags)
    # for k, v in num_brags.items():
    #     print(k, "=> ", v / num_calls)

    # percentage_returns = 0
    # TAKE_AT_TARGET = 5
    # for k, v in calls.items():
    #     percentage_returns += v["loss"]
    #     percentage_returns += v["take_profit"][TAKE_AT_TARGET - 1]
    #     # for idx, profit in enumerate(v["take_profit"]):
    #     #     percentage_returns += profit

    # print(percentage_returns / num_calls)


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
