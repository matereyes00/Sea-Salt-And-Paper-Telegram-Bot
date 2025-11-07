import os
import re
import logging
import traceback

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    CallbackQueryHandler,
)
# New imports for handling conversation history
from langchain_core.messages import HumanMessage, AIMessage
from utils.game_logic import calculate_score, calculate_color_bonus
from knowledge_base_manager import get_conversation_chain
from langchain_google_genai import ChatGoogleGenerativeAI
from utils.rag_pipeline import rag_pipeline

from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)

def escape_markdown(text) -> str:
    """Safely escape MarkdownV2 characters for Telegram, even if text isn't a string."""
    try:
        if text is None:
            return ""
        text = str(text)  # ensure string
        escape_chars = r'_*[]()~`>#+-=|{}.!'
        return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)
    except Exception as e:
        import traceback, logging
        logging.error(f"[escape_markdown] Failed for {type(text)}: {e}\n{traceback.format_exc()}")
        return str(text)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Greets the user and tells them the bot is ready."""
    text = "Hello! I am the Game Master 🤖🎲\nAsk me anything about the rules of the current game or use the /score and /color_bonus commands!"
    escaped_text = escape_markdown(text)
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=escaped_text,
        parse_mode=ParseMode.MARKDOWN_V2
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle messages from Telegram users."""
    logger.info("🟢 handle_message invoked")

    try:
        # Get message text
        message_text = update.message.text if update.message else None
        logger.info(f"📥 User message received: {repr(message_text)}")

        if not message_text:
            logger.warning("⚠️ No message text found in update.")
            return

        # 1. Lazy init the RAG chain (Retrieving vectorstore and passing it)
        if "conversation_chain" not in context.chat_data:
            logger.info("Initializing RAG chain on first use...")
            
            # Retrieve the vectorstore stored during the bot's setup (in setup_telegram_bot_local)
            vectorstore = context.bot_data.get("vectorstore") 
            if not vectorstore:
                    raise ValueError("Vectorstore not found in bot_data. Check setup_telegram_bot_local.")

            # Call the function from knowledge_base_manager with the vectorstore
            # NOTE: Assuming get_conversation_chain is imported from knowledge_base_manager.
            context.chat_data["conversation_chain"] = get_conversation_chain(vectorstore)
            logger.info("RAG chain initialized successfully.")

        conversation_chain = context.chat_data["conversation_chain"]

        # 2. Process the message (Correct Invocation)
        logger.info("💬 Invoking RAG chain...")
        
        # ConversationalRetrievalChain expects a dictionary input with the key 'question'.
        response = await conversation_chain.ainvoke({"question": message_text}) 
        
        logger.info(f"✅ RAG response: {repr(response)}")

        # 3. Extract the answer (Correct Extraction)
        # The ConversationalRetrievalChain returns a dict, with the answer under the 'answer' key.
        raw_answer = response.get("answer", str(response))
        answer = str(raw_answer).strip()
        logger.info(f"🧩 Final answer text ready: {repr(answer[:300])}")

        # Escape for Markdown
        logger.info("🔧 Escaping Markdown...")
        escaped_answer = escape_markdown(answer)
        logger.info(f"✅ Markdown escaped successfully: {escaped_answer[:300]}")

        # Send typing indicator first
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

        # Send response
        logger.info("📤 Sending message to Telegram...")
        await update.message.reply_text(
            escaped_answer,
            parse_mode="MarkdownV2"
        )
        logger.info("✅ Message successfully sent.")

    except Exception as e:
        logger.error(f"💥 Error during conversation chain invocation: {e}")
        logger.error(traceback.format_exc())

        # Send a user-friendly error message
        try:
            await update.message.reply_text(
                "⚠️ Sorry, I had trouble generating an answer. Please try again."
            )
        except Exception as nested_e:
            logger.error(f"Failed to send error message: {nested_e}")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Logs errors."""
    logger.error(f"An error occurred: {context.error}")

async def score(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Calculates the score for a list of cards."""
    user_input = update.message.text.partition(' ')[2]
    if not user_input:
        example_text = "Please list your cards after the command\\. \nExample: `/score 2 crabs, 4 shells`"
        await update.message.reply_text(text=example_text, parse_mode=ParseMode.MARKDOWN_V2)
        return
    response_text, _ = calculate_score(user_input)
    escaped_response = escape_markdown(response_text)
    await update.message.reply_text(text=escaped_response, parse_mode=ParseMode.MARKDOWN_V2)

async def color_bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Step 1: Ask user to choose the round outcome via inline buttons."""
    user_input = update.message.text.partition(' ')[2].strip()

    if not user_input:
        example_text = (
            "Please list your cards by color count. \n"
            "Example: `/color_bonus 4 blue, 3 pink, 1 mermaid`"
        )
        await update.message.reply_text(
            text=escape_markdown(example_text),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return

    # Save the card info temporarily (for callback use)
    context.user_data["color_bonus_input"] = user_input

    # Inline buttons for outcome selection
    keyboard = [
        [
            InlineKeyboardButton("Caller Win ✅ (You called + won)", callback_data="color_bonus_caller_win"),
            InlineKeyboardButton("Caller Fail ❌ (You called + lost)", callback_data="color_bonus_caller_fail"),
        ],
        [
            InlineKeyboardButton("Other Wins 🧍‍♂️ (Someone else called + won)", callback_data="color_bonus_other_win"),
            InlineKeyboardButton("Stop 🛑 (Normal end, no bonus)", callback_data="color_bonus_stop"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "Choose how the round ended:",
        reply_markup=reply_markup
    )


async def handle_color_bonus_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Step 2: Handle which color bonus scenario the user chose (with clarification text)."""
    query = update.callback_query
    await query.answer()  # Acknowledge button press

    user_input = context.user_data.get("color_bonus_input", "")
    if not user_input:
        await query.edit_message_text("⚠️ Please send `/color_bonus` again first.")
        return

    # Default flags
    called_last_chance, caller, caller_succeeded = True, True, True

    # --- Determine which option was chosen ---
    if query.data == "color_bonus_stop":
        called_last_chance = False
        clarification = "🛑 *Round ended normally with Stop* — no color bonus is scored."
    elif query.data == "color_bonus_caller_fail":
        caller_succeeded = False
        clarification = "❌ *You called Last Chance but lost* — you score only your color bonus."
    elif query.data == "color_bonus_other_win":
        caller = False
        caller_succeeded = True
        clarification = "🧍‍♂️ *Another player called Last Chance and succeeded* — you score only your color bonus."
    else:  # default: caller win
        clarification = "✅ *You called Last Chance and won* — you keep your full card points plus color bonus."

    # --- Compute color bonus using your logic ---
    bonus_points, explanation = calculate_color_bonus(
        user_input,
        called_last_chance=called_last_chance,
        caller=caller,
        caller_succeeded=caller_succeeded
    )

    # --- Combine clarification + result ---
    final_message = (
        f"{clarification}\n\n"
        f"🎨 *Color Bonus: {bonus_points} point(s)*\n\n"
        f"{explanation}"
    )

    escaped_response = escape_markdown(final_message)
    await query.edit_message_text(
        text=escaped_response,
        parse_mode=ParseMode.MARKDOWN_V2
    )


async def fetch_online_info_with_gemini(query: str):
    """Fetches supporting online info using Gemini."""
    try:
        gemini = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash-lite",
            temperature=0.7,
            google_api_key=os.getenv("GOOGLE_API_KEY")
        )

        prompt = (
            "Search for the most accurate and recent information about the card game and its expansion packs"
            "'Sea Salt & Paper'. Summarize it concisely. If there’s overlap with rulebook info, clarify it.\n\n"
            f"Question: {query}"
        )

        response = await gemini.ainvoke(prompt)
        return response.content if hasattr(response, "content") else str(response)
    
    except Exception as e:
        logger.error(f"Gemini fetch failed: {e}")
        return None


def setup_telegram_bot(vectorstore, port: int, webhook_url: str):
    """Initializes and runs the Telegram bot with webhooks."""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable not set!")

    app = Application.builder().token(bot_token).build()
    app.bot_data["vectorstore"] = vectorstore

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler('score', score))
    app.add_handler(CommandHandler('color_bonus', color_bonus))
    app.add_handler(CallbackQueryHandler(handle_color_bonus_choice, pattern="^color_bonus_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    logger.info(f"Starting webhook server on 0.0.0.0:{port}")
    app.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path=bot_token,
        webhook_url=f"{webhook_url}/{bot_token}"
    )

def setup_telegram_bot_local(vectorstore):
    """Initializes and runs the Telegram bot in polling mode for local development."""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable not set!")

    app = Application.builder().token(bot_token).build()
    app.bot_data["vectorstore"] = vectorstore

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler('score', score))
    app.add_handler(CommandHandler('color_bonus', color_bonus))
    app.add_handler(CallbackQueryHandler(handle_color_bonus_choice, pattern="^color_bonus_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)
    
    logger.info("Bot is running in polling mode...")
    # This command fetches updates from Telegram directly.
    app.run_polling()
