import datetime
from telethon import TelegramClient, events
from models import Trade
import os
from dotenv import load_dotenv
from parse_call import TradingCallParser
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from utils import setup_logger

dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path)

client = TelegramClient(
    "name", int(os.getenv("TELEGRAM_API_ID")), os.getenv("TELEGRAM_API_HASH")
)

# Create an engine that connects to the database
engine = create_engine("sqlite:///tradingbot.db")
session = sessionmaker(bind=engine)()
Trade.metadata.create_all(engine, checkfirst=True)

logger = setup_logger("tradingbot")


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


# save new messages as they arrive
@client.on(events.NewMessage(chats="Over99PercentWins"))
async def handler(event):
    filter_and_save(event.message)


def filter_and_save(message):
    if "setup" in message.text.lower():
        if not session.query(Trade).get(message.id):
            try:
                new_call = TradingCallParser().parse(message)
                if not is_duplicate(new_call):
                    session.add(new_call)
                    session.commit()
                    logger.info("New call => " + str(new_call))
            except Exception as e:
                logger.error("Could not parse call => " + str(message.id) + str(e))
        else:
            logger.debug("Already exists => " + str(message.id))
    else:
        if message.reply_to_msg_id:
            orig_call = session.query(Trade).get(message.reply_to_msg_id)
            if orig_call is not None and orig_call.bragged == 0:
                orig_call.bragged = 1
                session.commit()
                logger.info(f"Bragged/Cancelled => {message.reply_to_msg_id}")


# for debouncing duplicate calls
def is_duplicate(call: Trade):
    duplicate = (
        session.query(Trade)
        .filter(Trade.timestamp > call.timestamp - datetime.timedelta(minutes=5))
        .filter(Trade.texthash == call.texthash)
        .first()
    )
    if duplicate:
        return True
    else:
        return False


main()
client.run_until_disconnected()
