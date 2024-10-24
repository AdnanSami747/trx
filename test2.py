import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from telegram.error import BadRequest
from datetime import datetime, timedelta
import firebase_admin
from firebase_admin import credentials, firestore

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Telegram Bot Token
BOT_TOKEN = os.environ['7830769377:AAGvA9AZf3EJ3B1O1rpt6EkV2F2AYIbKfm0']  # Use Heroku environment variable

# Channel that users must join
CHANNEL_USERNAME = '@Tr3xxx3'

# Firebase configuration using Heroku environment variables
firebase_config = {
    "type": "service_account",
    "project_id": os.environ['FIREBASE_PROJECT_ID'],
    "private_key_id": os.environ['FIREBASE_PRIVATE_KEY_ID'],
    "private_key": os.environ['FIREBASE_PRIVATE_KEY'].replace('\\n', '\n'),  # Format Heroku key properly
    "client_email": os.environ['FIREBASE_CLIENT_EMAIL'],
    "token_uri": "https://oauth2.googleapis.com/token"
}

cred = credentials.Certificate(firebase_config)
firebase_admin.initialize_app(cred)
db = firestore.client()

# Command Handlers
async def start(update: Update, context):
    """Send a message asking the user to join the channel when the command /start is issued."""
    buttons = [
        [InlineKeyboardButton('🔗 Join Channel', url='https://t.me/Tr3xxx3')],
        [InlineKeyboardButton('✅ Joined', callback_data='check_joined')],
    ]
    keyboard = InlineKeyboardMarkup(buttons)
    await update.message.reply_text(
        "To use this bot, please join our channel first: https://t.me/Tr3xxx3",
        reply_markup=keyboard
    )

# Callback for button presses
async def button_callback(update: Update, context):
    query = update.callback_query
    await query.answer()

    if query.data == 'check_joined':
        user_id = query.from_user.id
        try:
            member = await context.bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
            if member.status in ['member', 'administrator', 'creator']:
                # Check if user exists in Firebase
                if not db.collection('users').document(str(user_id)).get().exists:
                    db.collection('users').document(str(user_id)).set({
                        'balance': 0,
                        'last_claim_time': None,
                        'referrals': 0
                    })

                buttons = [
                    [InlineKeyboardButton('💰 Daily Reward', callback_data='daily_reward')],
                    [InlineKeyboardButton('💵 Balance', callback_data='balance')],
                    [InlineKeyboardButton('👥 Invite Friend', callback_data='invite_friend')],
                    [InlineKeyboardButton('💎 Premium Plan', callback_data='premium_plan')],
                    [InlineKeyboardButton('💸 Withdraw', callback_data='withdraw')],
                ]
                keyboard = InlineKeyboardMarkup(buttons)
                await query.edit_message_text(
                    text="Thank you for joining the channel! You now have access to the bot's features.",
                    reply_markup=keyboard
                )
            else:
                await query.edit_message_text(
                    text="It seems you haven't joined the channel yet. Please join and click 'Joined' again."
                )
        except BadRequest:
            await query.edit_message_text(
                text="An error occurred. Make sure you have joined the channel and try again."
            )

# Helper to calculate remaining time for daily reward
def calculate_remaining_time(last_claim_time):
    next_claim_time = last_claim_time + timedelta(hours=24)
    remaining_time = next_claim_time - datetime.now()

    hours, remainder = divmod(remaining_time.total_seconds(), 3600)
    minutes, seconds = divmod(remainder, 60)
    return int(hours), int(minutes), int(seconds)

# Button handlers
async def feature_buttons(update: Update, context):
    query = update.callback_query
    user_id = str(query.from_user.id)

    await query.answer()

    if query.data == 'daily_reward':
        current_time = datetime.now()
        user_doc = db.collection('users').document(user_id)
        user_data = user_doc.get().to_dict()
        last_claim_time = user_data.get('last_claim_time')

        if last_claim_time:
            hours, minutes, seconds = calculate_remaining_time(last_claim_time)
            if current_time - last_claim_time < timedelta(hours=24):
                await query.edit_message_text(
                    text=f"You've already claimed your daily reward. Please come back in {hours}h {minutes}m {seconds}s."
                )
                return

        # Grant the reward (0.33 TRX)
        user_doc.update({
            'balance': firestore.Increment(0.33),
            'last_claim_time': current_time
        })

        await query.edit_message_text(
            text="You've received 0.33 TRX! Come back after 24 hours for the next reward."
        )

    elif query.data == 'balance':
        user_doc = db.collection('users').document(user_id)
        balance = user_doc.get().to_dict().get('balance')
        await query.edit_message_text(text=f"Your current balance is {balance} TRX")

    elif query.data == 'invite_friend':
        referral_link = f"https://t.me/your_bot_name?start={user_id}"  # Update with actual bot username
        await query.edit_message_text(
            text=f"Share this link with your friends: {referral_link}\nInvite 10 friends to join the bot and you'll receive 2 TRX!"
        )

    elif query.data == 'premium_plan':
        await premium_plan(update, context)

    elif query.data == 'withdraw':
        user_doc = db.collection('users').document(user_id)
        balance = user_doc.get().to_dict().get('balance')
        
        if balance >= 1:
            await query.edit_message_text(text="Please send your OKX TRX T20 wallet address:")
            context.user_data['awaiting_wallet'] = True
        else:
            await query.edit_message_text(
                text="You need a minimum balance of 1 TRX to withdraw."
            )

# Message handler for withdrawal
async def handle_message(update: Update, context):
    user_id = str(update.message.from_user.id)

    if context.user_data.get('awaiting_wallet'):
        wallet_address = update.message.text
        context.user_data['wallet_address'] = wallet_address
        await update.message.reply_text("How much TRX would you like to withdraw?")
        context.user_data['awaiting_wallet'] = False
        context.user_data['awaiting_amount'] = True
    elif context.user_data.get('awaiting_amount'):
        amount = float(update.message.text)
        user_doc = db.collection('users').document(user_id)
        user_data = user_doc.get().to_dict()
        balance = user_data.get('balance')

        if amount > balance:
            await update.message.reply_text("You cannot withdraw more than your current balance.")
        elif amount < 1:
            await update.message.reply_text("The minimum amount you can withdraw is 1 TRX.")
        else:
            user_doc.update({'balance': firestore.Increment(-amount)})
            wallet_address = context.user_data.get('wallet_address')
            await update.message.reply_text(f"Withdrawal of {amount} TRX to {wallet_address} has been processed.")
            context.user_data['awaiting_amount'] = False

# Premium plan functionality
async def premium_plan(update: Update, context):
    query = update.callback_query
    await query.answer()

    premium_text = (
        "Choose a premium plan:\n\n"
        "1️⃣ **Plan 1:** Pay $5 USDT for **3 TRX daily** for **5 months**.\n"
        "2️⃣ **Plan 2:** Pay $10 USDT for **7 TRX daily** for **10 months**.\n"
        "3️⃣ **Plan 3:** Pay $15 USDT for **12 TRX daily** for **17 months**.\n"
        "Click the 'BUY' button to proceed."
    )

    buttons = [
        [InlineKeyboardButton("Plan 1 - Buy", callback_data='buy_plan_1')],
        [InlineKeyboardButton("Plan 2 - Buy", callback_data='buy_plan_2')],
        [InlineKeyboardButton("Plan 3 - Buy", callback_data='buy_plan_3')],
        [InlineKeyboardButton("↩️ Back", callback_data='back')]
    ]
    keyboard = InlineKeyboardMarkup(buttons)

    await query.edit_message_text(text=premium_text, reply_markup=keyboard)

# Main function to run the bot
if __name__ == '__main__':
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler('start', start))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(CallbackQueryHandler(feature_buttons, pattern='^(daily_reward|balance|invite_friend|premium_plan|withdraw)$'))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Start polling
    application.run_polling()
